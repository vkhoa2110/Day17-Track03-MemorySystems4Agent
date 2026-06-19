from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Agent A: short-term memory only.

    Requirements:
    - Within-session memory only
    - No persistent `User.md`
    - Should forget long-term facts across new threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}

        # Optional live agent hook for local experiments.
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Return an answer using only this thread's short-term memory."""

        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.sessions.get(thread_id, SessionState()).token_usage

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.sessions.get(thread_id, SessionState()).prompt_tokens_processed

    def compaction_count(self, thread_id: str) -> int:
        # Baseline has no compact memory.
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Deterministic baseline path with no cross-thread memory."""

        session = self.sessions.setdefault(thread_id, SessionState())
        session.messages.append({"role": "user", "content": message})

        prompt_tokens = sum(estimate_tokens(item["content"]) for item in session.messages)
        facts = self._facts_for_thread(thread_id)
        answer = self._answer_from_thread_facts(message, facts)
        answer_tokens = estimate_tokens(answer)

        session.messages.append({"role": "assistant", "content": answer})
        session.token_usage += answer_tokens
        session.prompt_tokens_processed += prompt_tokens

        return {
            "answer": answer,
            "response": answer,
            "agent_tokens": answer_tokens,
            "prompt_tokens": prompt_tokens,
            "thread_id": thread_id,
            "compactions": 0,
        }

    def _maybe_build_langchain_agent(self):
        """Build the raw chat model if the caller wants to experiment live."""

        if self.force_offline:
            return None
        try:
            return build_chat_model(self.config.model)
        except (ImportError, ValueError):
            return None

    def _facts_for_thread(self, thread_id: str) -> dict[str, str]:
        session = self.sessions.get(thread_id)
        if not session:
            return {}

        facts: dict[str, str] = {}
        for item in session.messages:
            if item["role"] == "user":
                facts.update(extract_profile_updates(item["content"]))
        return facts

    def _answer_from_thread_facts(self, message: str, facts: dict[str, str]) -> str:
        lower = message.lower()
        if self._is_recall_question(lower) and not facts:
            return "Mình chưa có đủ thông tin trong thread này để trả lời chắc chắn."

        parts: list[str] = []

        if "tên" in lower and "name" in facts:
            parts.append(f"tên bạn là {facts['name']}")
        if ("đồ uống" in lower or "uống" in lower) and "favorite_drink" in facts:
            parts.append(f"đồ uống yêu thích là {facts['favorite_drink']}")
        if ("món ăn" in lower or "ăn yêu thích" in lower) and "favorite_food" in facts:
            parts.append(f"món ăn yêu thích là {facts['favorite_food']}")
        if ("nuôi" in lower or "corgi" in lower) and "pet" in facts:
            parts.append(f"bạn nuôi {facts['pet']}")
        if ("nghề" in lower or "làm gì" in lower or "làm nghề" in lower) and "profession" in facts:
            parts.append(f"nghề hiện tại là {facts['profession']}")
        if ("ở đâu" in lower or "nơi ở" in lower or "đang ở" in lower) and "location" in facts:
            parts.append(f"hiện bạn ở {facts['location']}")
        if ("style" in lower or "kiểu trả lời" in lower or "trả lời" in lower) and "response_style" in facts:
            parts.append(f"style trả lời bạn thích là {facts['response_style']}")
        if ("quan tâm" in lower or "mối quan tâm" in lower or "tóm tắt" in lower or "biết" in lower) and "technical_interests" in facts:
            parts.append(f"mối quan tâm chính là {facts['technical_interests']}")

        if parts:
            return "Trong thread này, " + "; ".join(parts) + "."

        if facts:
            return "Mình đã ghi nhận các thông tin này trong thread hiện tại."
        return "Mình đã nhận được tin nhắn, nhưng baseline không lưu trí nhớ dài hạn."

    @staticmethod
    def _is_recall_question(lower: str) -> bool:
        recall_markers = [
            "mình tên gì",
            "nhắc lại",
            "hiện tại mình",
            "bạn biết",
            "đồ uống",
            "món ăn",
            "nuôi con gì",
            "nghề",
            "ở đâu",
            "style",
            "kiểu trả lời",
            "tóm tắt",
        ]
        return "?" in lower or any(marker in lower for marker in recall_markers)
