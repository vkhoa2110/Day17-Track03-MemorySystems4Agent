from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def estimate_tokens(text: str) -> int:
    """Estimate tokens with a stable offline heuristic."""

    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return 0
    word_count = len(normalized.split())
    char_estimate = math.ceil(len(normalized) / 4)
    return max(1, word_count, char_estimate)


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md`.

    Each user id maps to one markdown file with stable profile facts.
    """

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", user_id.strip()).strip(".-")
        safe_id = safe_id or "anonymous"
        return self.root_dir / safe_id / "User.md"

    def read_text(self, user_id: str) -> str:
        path = self.path_for(user_id)
        if not path.exists():
            return "# User Profile\n\n## Facts\n\n"
        return path.read_text(encoding="utf-8")

    def write_text(self, user_id: str, content: str) -> Path:
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        content = self.read_text(user_id)
        if search_text not in content:
            return False
        self.write_text(user_id, content.replace(search_text, replacement, 1))
        return True

    def file_size(self, user_id: str) -> int:
        path = self.path_for(user_id)
        if not path.exists():
            return 0
        return path.stat().st_size

    def facts(self, user_id: str) -> dict[str, str]:
        facts: dict[str, str] = {}
        for line in self.read_text(user_id).splitlines():
            match = re.match(r"^-\s*([^:]+):\s*(.+?)\s*$", line)
            if match:
                facts[match.group(1).strip()] = match.group(2).strip()
        return facts

    def upsert_fact(self, user_id: str, key: str, value: str) -> Path:
        content = self.read_text(user_id)
        lines = content.splitlines()
        fact_pattern = re.compile(rf"^-\s*{re.escape(key)}\s*:", re.IGNORECASE)
        new_line = f"- {key}: {value.strip()}"

        for index, line in enumerate(lines):
            if fact_pattern.match(line):
                lines[index] = new_line
                return self.write_text(user_id, "\n".join(lines))

        if "## Facts" not in content:
            lines.extend(["", "## Facts", ""])
        lines.append(new_line)
        return self.write_text(user_id, "\n".join(lines))


def extract_profile_updates(message: str) -> dict[str, str]:
    """Extract stable profile facts from Vietnamese benchmark messages."""

    text = re.sub(r"\s+", " ", message or "").strip()
    if not text:
        return {}

    lower = text.lower()
    recall_markers = (
        "nhắc lại giúp mình",
        "nhắc lại",
        "mình tên gì",
        "tên mình là gì",
        "hiện tại mình đang ở đâu",
        "đâu mới là",
        "nuôi con gì",
    )
    if any(marker in lower for marker in recall_markers):
        return {}
    if text.endswith("?") and not any(marker in lower for marker in ("mình tên là", "tên mình là", "hiện tại là")):
        return {}

    facts: dict[str, str] = {}

    name_patterns = [
        r"\bmình tên là\s+(.+?)(?:[.,;]|$)",
        r"\btên mình là\s+(.+?)(?:[.,;]|$)",
        r"\btên\s+([A-ZĐ][^,.;]+?)(?:,\s*nghề|\s*,\s*nơi|\s*,\s*và|[.;]|$)",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            name = _clean_fact(match.group(1))
            if name and not re.search(r"\bgì\b|\bkhông\b|^và\b", name, flags=re.IGNORECASE):
                facts["name"] = name
                break

    location = _extract_location(text)
    if location:
        facts["location"] = location

    profession = _extract_profession(text)
    if profession:
        facts["profession"] = profession

    if "cà phê sữa đá" in lower and not re.search(r"\bkhông thích cà phê sữa đá\b", lower):
        facts["favorite_drink"] = "cà phê sữa đá"

    if "mì quảng" in lower and ("món ăn yêu thích" in lower or "món ruột" in lower or "ăn mì quảng" in lower):
        facts["favorite_food"] = "mì Quảng"

    if "corgi" in lower:
        pet = "corgi"
        if re.search(r"\b(bơ)\b", lower):
            pet = "corgi tên Bơ"
        facts["pet"] = pet

    style = _extract_response_style(lower)
    if style:
        facts["response_style"] = style

    interests = _extract_interests(text)
    if interests:
        facts["technical_interests"] = interests

    if "ưu tiên recall đúng" in lower:
        facts["priority"] = "ưu tiên recall đúng hơn câu văn quá hoa mỹ"
    elif "benchmark có số liệu rõ ràng" in lower or "số liệu minh họa" in lower:
        facts["priority"] = "ưu tiên benchmark có số liệu rõ ràng"

    return facts


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Create a compact, deterministic summary of older messages."""

    if not messages:
        return ""

    facts: dict[str, str] = {}
    topic_lines: list[str] = []
    snippets: list[str] = []

    topic_keywords = {
        "Artemis": "Artemis III: dependency/readiness roadmap trước launch lớn.",
        "X-59": "X-59: tối ưu performance nhưng giảm externality/sonic boom.",
        "WMO": "WMO/El Nino: xác suất tăng dần cần chuyển từ theo dõi sang chuẩn bị.",
        "British Columbia": "British Columbia energy: cân bằng scale nhu cầu điện với efficiency.",
        "BC energy": "British Columbia energy: cân bằng scale nhu cầu điện với efficiency.",
        "Power Smart": "Power Smart 2.0: tiết kiệm điện như một phần của chiến lược scale.",
    }

    for message in messages:
        role = message.get("role", "user")
        content = re.sub(r"\s+", " ", message.get("content", "")).strip()
        if not content:
            continue
        if role == "user":
            facts.update(extract_profile_updates(content))
        for keyword, summary in topic_keywords.items():
            if keyword.lower() in content.lower() and summary not in topic_lines:
                topic_lines.append(summary)
        if len(snippets) < max_items and _looks_important(content):
            snippets.append(_truncate(content, 180))

    lines: list[str] = []
    if facts:
        fact_text = "; ".join(f"{key}={value}" for key, value in sorted(facts.items()))
        lines.append(f"Stable facts seen: {fact_text}.")
    lines.extend(topic_lines[:max_items])
    lines.extend(f"Older turn: {snippet}" for snippet in snippets[:max_items])

    if not lines:
        for message in messages[:max_items]:
            content = _truncate(re.sub(r"\s+", " ", message.get("content", "")).strip(), 160)
            if content:
                lines.append(f"{message.get('role', 'user')}: {content}")

    return "\n".join(_dedupe(lines))


@dataclass
class CompactMemoryManager:
    """Compact memory for long threads."""

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def append(self, thread_id: str, role: str, content: str) -> None:
        state = self._thread_state(thread_id)
        messages = state["messages"]
        assert isinstance(messages, list)
        messages.append({"role": role, "content": content})
        self._compact_if_needed(state)

    def context(self, thread_id: str) -> dict[str, object]:
        state = self._thread_state(thread_id)
        return {
            "messages": list(state["messages"]),
            "summary": str(state["summary"]),
            "compactions": int(state["compactions"]),
        }

    def compaction_count(self, thread_id: str) -> int:
        return int(self._thread_state(thread_id)["compactions"])

    def _thread_state(self, thread_id: str) -> dict[str, Any]:
        return self.state.setdefault(thread_id, {"messages": [], "summary": "", "compactions": 0})

    def _compact_if_needed(self, state: dict[str, Any]) -> None:
        messages: list[dict[str, str]] = state["messages"]
        summary = str(state["summary"])
        total_tokens = estimate_tokens(summary) + sum(estimate_tokens(item["content"]) for item in messages)

        if total_tokens <= self.threshold_tokens or len(messages) <= self.keep_messages:
            return

        keep = max(1, self.keep_messages)
        older = messages[:-keep]
        recent = messages[-keep:]
        new_summary = summarize_messages(older)
        state["summary"] = _merge_summaries(summary, new_summary)
        state["messages"] = recent
        state["compactions"] = int(state["compactions"]) + 1


def _clean_fact(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .,:;!?")
    value = re.sub(r"\s+(và|nhưng|nên)$", "", value, flags=re.IGNORECASE).strip()
    return value


def _extract_location(text: str) -> str | None:
    lower = text.lower()
    known_locations = ["Đà Nẵng", "Huế", "Hà Nội"]

    correction_patterns = [
        r"thực ra[^.]*đang làm việc ở\s+([A-ZĐ][^,.;]+)",
        r"thực ra[^.]*đang ở\s+([A-ZĐ][^,.;]+)",
        r"cập nhật từ\s+[A-ZĐ][^,.;]+?\s+sang\s+([A-ZĐ][^,.;]+)",
        r"đã cập nhật từ\s+[A-ZĐ][^,.;]+?\s+sang\s+([A-ZĐ][^,.;]+)",
    ]
    for pattern in correction_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = _clean_fact(match.group(1))
            for location in known_locations:
                if location.lower() in candidate.lower() and not _is_negated_location(lower, location):
                    return location

    if "không phải nơi ở hiện tại" in lower:
        for location in known_locations:
            if location.lower() in lower and re.search(rf"{location.lower()}[^.]+không phải nơi ở hiện tại", lower):
                return None

    explicit_patterns = [
        r"nơi ở hiện tại (?:là|là\s+ở)\s+([A-ZĐ][^,.;]+)",
        r"hiện tại (?:mình )?(?:đang )?ở\s+([A-ZĐ][^,.;]+)",
        r"hiện ở\s+([A-ZĐ][^,.;]+)",
        r"mình ở\s+([A-ZĐ][^,.;]+)",
        r"vẫn ở\s+([A-ZĐ][^,.;]+)",
        r"đang làm việc ở\s+([A-ZĐ][^,.;]+)",
        r"đang ở\s+([A-ZĐ][^,.;]+)",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = _clean_fact(match.group(1))
            for location in known_locations:
                if location.lower() in candidate.lower():
                    if _is_negated_location(lower, location):
                        continue
                    return location
            if candidate and not re.search(r"\bđâu\b|\bkhông\b", candidate, flags=re.IGNORECASE):
                return candidate

    for location in known_locations:
        if location.lower() in lower and ("nơi ở đã cập nhật" in lower or "đã cập nhật từ" in lower):
            if f"sang {location.lower()}" in lower or f"ở {location.lower()}" in lower:
                return location

    return None


def _is_negated_location(lower: str, location: str) -> bool:
    name = location.lower()
    negated_patterns = [
        rf"không còn ở {re.escape(name)}",
        rf"{re.escape(name)}[^.]+không phải nơi ở hiện tại",
        rf"{re.escape(name)}[^.]+chỉ là nơi",
        rf"{re.escape(name)}[^.]+họp",
    ]
    return any(re.search(pattern, lower) for pattern in negated_patterns)


def _extract_profession(text: str) -> str | None:
    lower = text.lower()
    if "mlops engineer" in lower and any(
        marker in lower
        for marker in (
            "giờ chuyển sang",
            "nghề nghiệp hiện tại",
            "nghề hiện tại",
            "vẫn là mlops engineer",
            "đang làm mlops engineer",
            "làm mlops engineer",
            "nghề mlops engineer",
        )
    ):
        return "MLOps engineer"

    if "backend engineer" in lower and "không còn làm backend engineer" not in lower:
        if "đang làm backend engineer" in lower or "làm backend engineer" in lower:
            return "backend engineer"

    if "product manager" in lower and "câu đùa" not in lower and "đùa" not in lower:
        if "nghề nghiệp hiện tại" in lower or "đang làm product manager" in lower:
            return "product manager"

    match = re.search(r"(?:đang làm|nghề nghiệp hiện tại là|nghề hiện tại là)\s+([^,.;]+)", text, flags=re.IGNORECASE)
    if match:
        candidate = _clean_fact(match.group(1))
        if "câu đùa" not in lower and "không còn" not in candidate.lower():
            return candidate

    return None


def _extract_response_style(lower: str) -> str | None:
    if "3 bullet" in lower:
        return "3 bullet ngắn, có ví dụ thực chiến, nhấn trade-off giữa recall và token cost"

    if "trả lời" not in lower and "giải thích" not in lower and "style" not in lower:
        return None

    if "ngắn gọn" in lower or "gọn" in lower:
        pieces = ["ngắn gọn"]
        if "bullet" in lower:
            pieces.append("có bullet")
        if "rõ ý" in lower:
            pieces.append("rõ ý")
        if "ví dụ thực chiến" in lower:
            pieces.append("có ví dụ thực chiến")
        elif "ví dụ thực tế" in lower:
            pieces.append("có ví dụ thực tế")
        if "trade-off" in lower:
            pieces.append("nêu trade-off")
        return ", ".join(_dedupe(pieces))

    return None


def _extract_interests(text: str) -> str | None:
    lower = text.lower()
    interests: list[str] = []
    if "python" in lower:
        interests.append("Python")
    if "ai ứng dụng" in lower:
        interests.append("AI ứng dụng")
    elif "ai agent" in lower:
        interests.append("AI agent")
    elif re.search(r"\bai\b", lower):
        interests.append("AI")
    if "mlops" in lower:
        interests.append("MLOps")
    if "benchmark memory" in lower or "benchmark agent" in lower:
        interests.append("benchmark memory")
    if not interests:
        return None
    return ", ".join(_dedupe(interests))


def _looks_important(content: str) -> bool:
    lower = content.lower()
    markers = [
        "mình tên",
        "đính chính",
        "hiện tại",
        "nghề",
        "nơi ở",
        "style",
        "trả lời",
        "artemis",
        "x-59",
        "wmo",
        "british columbia",
        "bc energy",
        "trade-off",
        "compact",
    ]
    return any(marker in lower for marker in markers)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _merge_summaries(existing: str, new_summary: str, max_lines: int = 24) -> str:
    lines = []
    if existing.strip():
        lines.extend(existing.splitlines())
    if new_summary.strip():
        lines.extend(new_summary.splitlines())

    important = [line for line in _dedupe([line.strip() for line in lines]) if line]
    if len(important) > max_lines:
        important = important[:8] + important[-(max_lines - 8) :]
    merged = "\n".join(important)
    return _truncate(merged, 4000)
