"""Shared validation helpers for RAG modules."""

from __future__ import annotations


def validate_question(question: str) -> str:
    """Return a stripped non-empty question or raise a clear error."""

    if not isinstance(question, str):
        raise TypeError("question must be a string")
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question cannot be empty or whitespace")
    return clean_question
