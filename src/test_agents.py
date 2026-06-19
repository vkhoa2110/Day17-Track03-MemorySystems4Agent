from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config
from memory_store import CompactMemoryManager, UserProfileStore


def make_config(tmp_path: Path):
    """Build an isolated config for tests."""

    config = load_config(Path(__file__).resolve().parent.parent)
    config.state_dir = tmp_path / "state"
    config.state_dir.mkdir(parents=True, exist_ok=True)
    config.compact_threshold_tokens = 90
    config.compact_keep_messages = 4
    return config


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Verify `User.md` can be created, updated, and edited."""

    store = UserProfileStore(tmp_path / "profiles")

    assert "User Profile" in store.read_text("dung/ct")

    path = store.write_text("dung/ct", "# User Profile\n\n## Facts\n\n- profession: backend engineer\n")
    assert path.exists()
    assert path.name == "User.md"

    changed = store.edit_text("dung/ct", "backend engineer", "MLOps engineer")

    assert changed is True
    assert "MLOps engineer" in store.read_text("dung/ct")
    assert store.file_size("dung/ct") > 0


def test_compact_trigger(tmp_path: Path) -> None:
    """Verify long threads trigger compaction."""

    del tmp_path
    manager = CompactMemoryManager(threshold_tokens=40, keep_messages=2)

    for index in range(8):
        manager.append(
            "thread-1",
            "user",
            f"Turn {index}: mình đang viết một đoạn rất dài về compact memory và token cost để ép nén lịch sử.",
        )

    context = manager.context("thread-1")

    assert manager.compaction_count("thread-1") > 0
    assert context["summary"]
    assert len(context["messages"]) <= 2


def test_cross_session_recall(tmp_path: Path) -> None:
    """Verify advanced remembers across sessions and baseline does not."""

    config = make_config(tmp_path)
    advanced = AdvancedAgent(config=config, force_offline=True)
    baseline = BaselineAgent(config=config, force_offline=True)

    for agent in (advanced, baseline):
        agent.reply("dungct", "session-1", "Chào bạn, mình tên là DũngCT.")
        agent.reply("dungct", "session-1", "Mình không còn làm backend engineer nữa, giờ chuyển sang MLOps engineer.")

    advanced_answer = advanced.reply("dungct", "session-2", "Mình tên gì và hiện làm nghề gì?")["answer"]
    baseline_answer = baseline.reply("dungct", "session-2", "Mình tên gì và hiện làm nghề gì?")["answer"]

    assert "DũngCT" in advanced_answer
    assert "MLOps engineer" in advanced_answer
    assert "DũngCT" not in baseline_answer
    assert "MLOps engineer" not in baseline_answer


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Compare prompt load of baseline vs advanced on a long thread."""

    config = make_config(tmp_path)
    advanced = AdvancedAgent(config=config, force_offline=True)
    baseline = BaselineAgent(config=config, force_offline=True)

    for index in range(16):
        message = (
            f"Turn {index}: mình đang stress test memory system với một đoạn dài về Python, "
            "AI agent, prompt tokens processed, compact summary và trade-off giữa recall đúng "
            "với chi phí context trong hệ thống MLOps thực tế."
        )
        baseline.reply("dungct", "long-thread", message)
        advanced.reply("dungct", "long-thread", message)

    assert advanced.compaction_count("long-thread") > 0
    assert advanced.prompt_token_usage("long-thread") < baseline.prompt_token_usage("long-thread")
