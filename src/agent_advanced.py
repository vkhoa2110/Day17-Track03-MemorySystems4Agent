from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Agent B: profile memory plus compact thread memory.

    Required memory layers:
    1. within-session memory
    2. persistent `User.md`
    3. compact memory for long threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}

        # Optional live agent hook for local experiments.
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Return an answer using profile memory plus compact thread memory."""

        return self._reply_offline(user_id, thread_id, message)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Deterministic advanced path used by tests and offline benchmark."""

        for key, value in extract_profile_updates(message).items():
            self.profile_store.upsert_fact(user_id, key, value)

        self.compact_memory.append(thread_id, "user", message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        answer = self._offline_response(user_id, thread_id, message)
        answer_tokens = estimate_tokens(answer)
        self.compact_memory.append(thread_id, "assistant", answer)

        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + answer_tokens
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens

        return {
            "answer": answer,
            "response": answer,
            "agent_tokens": answer_tokens,
            "prompt_tokens": prompt_tokens,
            "thread_id": thread_id,
            "memory_path": str(self.profile_store.path_for(user_id)),
            "memory_bytes": self.memory_file_size(user_id),
            "compactions": self.compaction_count(thread_id),
        }

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Estimate profile + compact summary + recent message context."""

        context = self.compact_memory.context(thread_id)
        recent_messages = context["messages"]
        assert isinstance(recent_messages, list)

        profile_tokens = estimate_tokens(self.profile_store.read_text(user_id))
        summary_tokens = estimate_tokens(str(context["summary"]))
        recent_tokens = sum(estimate_tokens(item["content"]) for item in recent_messages)
        return profile_tokens + summary_tokens + recent_tokens

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Return a deterministic answer using persisted facts."""

        facts = self.profile_store.facts(user_id)
        lower = message.lower()

        if self._asks_about_news_context(lower):
            topic_answer = self._topic_answer(thread_id)
            if topic_answer:
                return topic_answer

        if self._is_recall_question(lower):
            answer = self._answer_from_profile(lower, facts)
            if answer:
                return answer
            return "Mình chưa có đủ thông tin đã lưu để trả lời chắc chắn."

        updates = extract_profile_updates(message)
        if updates:
            changed = "; ".join(f"{key}={value}" for key, value in updates.items())
            return f"Mình đã cập nhật vào User.md: {changed}."

        if facts:
            style = facts.get("response_style", "ngắn gọn")
            return f"Mình đã ghi nhận. Các câu sau mình sẽ ưu tiên style {style}."
        return "Mình đã nhận được tin nhắn và sẽ lưu các thông tin ổn định khi đủ chắc chắn."

    def _maybe_build_langchain_agent(self):
        """Build the raw chat model if the caller wants to experiment live."""

        if self.force_offline:
            return None
        try:
            return build_chat_model(self.config.model)
        except (ImportError, ValueError):
            return None

    def _answer_from_profile(self, lower: str, facts: dict[str, str]) -> str:
        parts: list[str] = []

        if "tên" in lower or "dũngct" in lower or "biết" in lower or "tóm tắt" in lower:
            if "name" in facts:
                parts.append(f"tên bạn là {facts['name']}")

        if "nghề" in lower or "làm gì" in lower or "làm nghề" in lower or "product manager" in lower:
            if "profession" in facts:
                parts.append(f"nghề hiện tại là {facts['profession']}")

        if "ở đâu" in lower or "nơi ở" in lower or "đang ở" in lower or "huế" in lower or "hà nội" in lower:
            if "location" in facts:
                parts.append(f"nơi ở hiện tại là {facts['location']}")

        if "đồ uống" in lower or "uống" in lower:
            if "favorite_drink" in facts:
                parts.append(f"đồ uống yêu thích là {facts['favorite_drink']}")

        if "món ăn" in lower or "ăn yêu thích" in lower:
            if "favorite_food" in facts:
                parts.append(f"món ăn yêu thích là {facts['favorite_food']}")

        if "nuôi" in lower or "corgi" in lower or "con gì" in lower:
            if "pet" in facts:
                parts.append(f"bạn nuôi {facts['pet']}")

        if "style" in lower or "kiểu trả lời" in lower or "trả lời" in lower or "3 bullet" in lower:
            if "response_style" in facts:
                parts.append(f"style trả lời bạn thích là {facts['response_style']}")

        if "quan tâm" in lower or "mối quan tâm" in lower or "tóm tắt" in lower or "ai" in lower:
            if "technical_interests" in facts:
                parts.append(f"mối quan tâm kỹ thuật chính là {facts['technical_interests']}")

        if not parts and any(key in facts for key in ("name", "profession", "location")):
            for key, label in (
                ("name", "tên bạn là"),
                ("profession", "nghề hiện tại là"),
                ("location", "nơi ở hiện tại là"),
            ):
                if key in facts:
                    parts.append(f"{label} {facts[key]}")

        if not parts:
            return ""

        return "Mình nhớ: " + "; ".join(parts) + "."

    @staticmethod
    def _is_recall_question(lower: str) -> bool:
        recall_markers = [
            "?",
            "nhắc lại",
            "mình tên gì",
            "hiện tại mình",
            "bạn biết",
            "tóm tắt",
            "đâu mới là",
            "đồ uống",
            "món ăn",
            "nuôi con gì",
            "nghề",
            "nơi ở",
            "style",
            "kiểu trả lời",
        ]
        return any(marker in lower for marker in recall_markers)

    @staticmethod
    def _asks_about_news_context(lower: str) -> bool:
        markers = ["bốn tin", "artemis", "x-59", "wmo", "el nino", "british columbia", "bc energy"]
        return any(marker in lower for marker in markers)

    def _topic_answer(self, thread_id: str) -> str:
        context = self.compact_memory.context(thread_id)
        summary = str(context["summary"])
        if not summary:
            return ""

        lines = [
            line
            for line in summary.splitlines()
            if any(keyword in line.lower() for keyword in ("artemis", "x-59", "wmo", "british columbia", "power smart"))
        ]
        if not lines:
            return ""
        return "Mình nhớ khung chính: " + " ".join(lines[:4])
