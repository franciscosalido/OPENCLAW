"""Shared validation for OpenAI-compatible chat messages."""

from __future__ import annotations

from collections.abc import Sequence


VALID_CHAT_ROLES = frozenset({"system", "user", "assistant"})


def validate_chat_messages(messages: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """Validate and normalize chat messages without logging their contents."""
    if not messages:
        raise ValueError("messages cannot be empty")

    clean_messages: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role", "").strip()
        content = message.get("content", "").strip()
        if role not in VALID_CHAT_ROLES:
            raise ValueError("message role must be system, user, or assistant")
        if not content:
            raise ValueError("message content cannot be empty")
        clean_messages.append({"role": role, "content": content})
    return clean_messages
