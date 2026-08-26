from typing import Any

MAX_TURNS = 10
MAX_CHARS_PER_TURN = 1200

_ROLES = {"user", "assistant"}


def sanitise_history(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []

    turns: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in _ROLES or not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        turns.append({"role": role, "content": text[:MAX_CHARS_PER_TURN]})

    trimmed = turns[-MAX_TURNS:]
    while trimmed and trimmed[0]["role"] == "assistant":
        trimmed.pop(0)
    return trimmed
