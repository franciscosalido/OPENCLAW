"""Safe local parsers for controlled corpus ingestion."""

from __future__ import annotations

from importlib import import_module, util
from pathlib import Path
from typing import Any, cast


class ParserUnavailableError(RuntimeError):
    """Raised when the parser dependency for a source type is unavailable."""


class ParserRejectedError(RuntimeError):
    """Raised when parsing fails for a safe, reportable reason."""


def parse_md(path: Path) -> str:
    """Parse Markdown as UTF-8 text."""

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ParserRejectedError("parser_error") from exc
    except OSError as exc:
        raise ParserRejectedError("parser_error") from exc


def parse_pdf(path: Path) -> str:
    """Parse PDF text locally with pypdf when available; no OCR."""

    if util.find_spec("pypdf") is None:
        raise ParserUnavailableError("parser_unavailable")

    try:
        pypdf = import_module("pypdf")
        reader_cls = cast(Any, pypdf).PdfReader
        reader = reader_cls(str(path))
        page_texts = [str(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise ParserRejectedError("parser_error") from exc

    return "\n".join(page_texts)


def parse_document(path: Path, source_type: str) -> str:
    """Parse a supported corpus document."""

    if source_type == "md":
        return parse_md(path)
    if source_type == "pdf":
        return parse_pdf(path)
    raise ParserRejectedError("unsupported_source_type")

