"""Chunk text for local RAG ingestion.

The chunker is pure Python and dependency-free. It prefers paragraph boundaries,
falls back to multilingual sentence boundaries, and prefixes each chunk after the
first with a configurable overlap from the previous chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


DEFAULT_MAX_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 80

_TOKEN_RE = re.compile(r"\S+")
_PARAGRAPH_RE = re.compile(r"\S[\s\S]*?(?=\n\s*\n|\Z)")
_SENTENCE_RE = re.compile(r"[^.!?…。！？]+(?:[.!?…。！？]+|$)", re.UNICODE)


@dataclass(frozen=True)
class Chunk:
    """A source text chunk ready for embedding."""

    text: str
    index: int
    start_char: int
    end_char: int


@dataclass(frozen=True)
class _TextUnit:
    text: str
    start_char: int
    end_char: int
    token_count: int


def chunk_text(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Split text into chunks with configurable overlap.

    Tokens are approximated with non-whitespace spans. This keeps the
    implementation deterministic and dependency-free for RAG-0.
    """

    _validate_options(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    if not text or not text.strip():
        return []

    units = _split_text_units(text, max_tokens=max_tokens)
    chunks: list[Chunk] = []
    current_units: list[_TextUnit] = []
    current_tokens = 0
    previous_body = ""

    for unit in units:
        would_exceed = current_units and current_tokens + unit.token_count > max_tokens
        if would_exceed:
            chunk, previous_body = _build_chunk(
                index=len(chunks),
                units=current_units,
                overlap_tokens=overlap_tokens,
                previous_body=previous_body,
            )
            chunks.append(chunk)
            current_units = []
            current_tokens = 0

        current_units.append(unit)
        current_tokens += unit.token_count

    if current_units:
        chunk, _previous_body = _build_chunk(
            index=len(chunks),
            units=current_units,
            overlap_tokens=overlap_tokens,
            previous_body=previous_body,
        )
        chunks.append(chunk)

    return chunks


def _validate_options(max_tokens: int, overlap_tokens: int) -> None:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")


def _split_text_units(text: str, max_tokens: int) -> list[_TextUnit]:
    units: list[_TextUnit] = []

    for paragraph_match in _PARAGRAPH_RE.finditer(text):
        paragraph = _trim_unit(
            text=paragraph_match.group(0),
            start_char=paragraph_match.start(),
            end_char=paragraph_match.end(),
        )
        if paragraph is None:
            continue

        if _count_tokens(paragraph.text) <= max_tokens:
            units.append(paragraph)
            continue

        units.extend(_split_large_paragraph(paragraph, max_tokens=max_tokens))

    return units


def _split_large_paragraph(paragraph: _TextUnit, max_tokens: int) -> list[_TextUnit]:
    sentence_units: list[_TextUnit] = []

    for sentence_match in _SENTENCE_RE.finditer(paragraph.text):
        absolute_start = paragraph.start_char + sentence_match.start()
        absolute_end = paragraph.start_char + sentence_match.end()
        sentence = _trim_unit(
            text=sentence_match.group(0),
            start_char=absolute_start,
            end_char=absolute_end,
        )
        if sentence is None:
            continue

        if sentence.token_count <= max_tokens:
            sentence_units.append(sentence)
        else:
            sentence_units.extend(_split_large_sentence(sentence, max_tokens=max_tokens))

    return sentence_units


def _split_large_sentence(sentence: _TextUnit, max_tokens: int) -> list[_TextUnit]:
    token_matches = list(_TOKEN_RE.finditer(sentence.text))
    units: list[_TextUnit] = []

    for start_index in range(0, len(token_matches), max_tokens):
        group = token_matches[start_index : start_index + max_tokens]
        absolute_start = sentence.start_char + group[0].start()
        absolute_end = sentence.start_char + group[-1].end()
        unit_text = sentence.text[group[0].start() : group[-1].end()]
        units.append(
            _TextUnit(
                text=unit_text,
                start_char=absolute_start,
                end_char=absolute_end,
                token_count=len(group),
            )
        )

    return units


def _trim_unit(text: str, start_char: int, end_char: int) -> _TextUnit | None:
    left_trimmed = len(text) - len(text.lstrip())
    right_trimmed = len(text.rstrip())
    trimmed_text = text.strip()

    if not trimmed_text:
        return None

    trimmed_start = start_char + left_trimmed
    trimmed_end = start_char + right_trimmed
    return _TextUnit(
        text=trimmed_text,
        start_char=trimmed_start,
        end_char=trimmed_end,
        token_count=_count_tokens(trimmed_text),
    )


def _build_chunk(
    index: int,
    units: list[_TextUnit],
    overlap_tokens: int,
    previous_body: str,
) -> tuple[Chunk, str]:
    body = "\n\n".join(unit.text for unit in units)
    chunk_text_value = body

    if index > 0 and overlap_tokens:
        overlap = _last_tokens(previous_body, overlap_tokens)
        if overlap:
            chunk_text_value = f"{overlap}\n\n{body}"

    return Chunk(
        text=chunk_text_value,
        index=index,
        start_char=units[0].start_char,
        end_char=units[-1].end_char,
    ), body


def _count_tokens(text: str) -> int:
    return len(_TOKEN_RE.findall(text))


def _last_tokens(text: str, token_count: int) -> str:
    tokens = _TOKEN_RE.findall(text)
    return " ".join(tokens[-token_count:])
