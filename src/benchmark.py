from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Read JSON conversations from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def recall_points(answer: str, expected: list[str]) -> float:
    """Return the fraction of expected facts present in the answer."""

    if not expected:
        return 1.0
    normalized_answer = answer.lower()
    matched = sum(1 for item in expected if item.lower() in normalized_answer)
    return matched / len(expected)


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Lightweight quality score for deterministic offline responses."""

    recall = recall_points(answer, expected)
    words = answer.split()
    if 5 <= len(words) <= 90:
        shape_score = 1.0
    elif len(words) < 5:
        shape_score = 0.6
    else:
        shape_score = 0.75
    return round((0.8 * recall) + (0.2 * shape_score), 3)


def run_agent_benchmark(agent_name: str, agent, conversations: list[dict[str, Any]], config) -> BenchmarkRow:
    """Evaluate one agent over many conversations."""

    del config

    user_ids = sorted({conversation["user_id"] for conversation in conversations})
    memory_before = _total_memory_size(agent, user_ids)
    agent_tokens_only = 0
    prompt_tokens_processed = 0
    recall_scores: list[float] = []
    quality_scores: list[float] = []
    touched_threads: set[str] = set()

    for conversation in conversations:
        user_id = conversation["user_id"]
        thread_id = conversation["id"]
        touched_threads.add(thread_id)

        for turn in conversation.get("turns", []):
            result = agent.reply(user_id=user_id, thread_id=thread_id, message=turn)
            agent_tokens_only += int(result.get("agent_tokens", 0))
            prompt_tokens_processed += int(result.get("prompt_tokens", 0))

        for index, recall_question in enumerate(conversation.get("recall_questions", []), start=1):
            recall_thread = f"{thread_id}-recall-{index}"
            touched_threads.add(recall_thread)
            result = agent.reply(
                user_id=user_id,
                thread_id=recall_thread,
                message=recall_question["question"],
            )
            answer = result["answer"]
            expected = recall_question.get("expected_contains", [])
            agent_tokens_only += int(result.get("agent_tokens", 0))
            prompt_tokens_processed += int(result.get("prompt_tokens", 0))
            recall_scores.append(recall_points(answer, expected))
            quality_scores.append(heuristic_quality(answer, expected))

    memory_after = _total_memory_size(agent, user_ids)
    compactions = sum(_compaction_count(agent, thread_id) for thread_id in touched_threads)

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=agent_tokens_only,
        prompt_tokens_processed=prompt_tokens_processed,
        recall_score=round(_mean(recall_scores), 3),
        response_quality=round(_mean(quality_scores), 3),
        memory_growth_bytes=max(0, memory_after - memory_before),
        compactions=compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Format benchmark rows as a markdown table."""

    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth (bytes)",
        "Compactions",
    ]
    body = [
        [
            row.agent_name,
            row.agent_tokens_only,
            row.prompt_tokens_processed,
            f"{row.recall_score:.3f}",
            f"{row.response_quality:.3f}",
            row.memory_growth_bytes,
            row.compactions,
        ]
        for row in rows
    ]

    try:
        from tabulate import tabulate
    except ImportError:
        tabulate = None

    if tabulate:
        return tabulate(body, headers=headers, tablefmt="github")

    table = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in body:
        table.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(table)


def main() -> None:
    """Run both benchmark suites.

    Required benchmark sections:
    - Standard benchmark from `data/conversations.json`
    - Long-context stress benchmark from `data/advanced_long_context.json`

    Compare:
    - Baseline
    - Advanced

    Keep the same output columns as the solved lab:
    - Agent tokens only
    - Prompt tokens processed
    - Cross-session recall
    - Response quality
    - Memory growth (bytes)
    - Compactions
    """

    config = load_config(Path(__file__).resolve().parent.parent)
    run_state_dir = config.state_dir / "benchmark_runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_state_dir.mkdir(parents=True, exist_ok=True)
    config = replace(config, state_dir=run_state_dir)

    suites = [
        ("Standard Benchmark", config.data_dir / "conversations.json"),
        ("Long-Context Stress Benchmark", config.data_dir / "advanced_long_context.json"),
    ]

    for suite_name, path in suites:
        conversations = load_conversations(path)
        rows = [
            run_agent_benchmark(
                "Baseline",
                BaselineAgent(config=config, force_offline=True),
                conversations,
                config,
            ),
            run_agent_benchmark(
                "Advanced",
                AdvancedAgent(config=config, force_offline=True),
                conversations,
                config,
            ),
        ]
        print(f"\n## {suite_name}\n")
        print(format_rows(rows))


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _total_memory_size(agent, user_ids: list[str]) -> int:
    if not hasattr(agent, "memory_file_size"):
        return 0
    return sum(int(agent.memory_file_size(user_id)) for user_id in user_ids)


def _compaction_count(agent, thread_id: str) -> int:
    if not hasattr(agent, "compaction_count"):
        return 0
    return int(agent.compaction_count(thread_id))


if __name__ == "__main__":
    main()
