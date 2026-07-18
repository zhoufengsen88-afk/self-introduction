import hashlib
import re
from typing import Any

from .models import DocumentMetadata

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
REQUIRED_FIELDS = {
    "document_id",
    "title",
    "category",
    "visibility",
    "status",
    "updated_at",
}


class FrontMatterError(ValueError):
    pass


def parse_front_matter(text: str) -> tuple[DocumentMetadata, str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise FrontMatterError("missing YAML front matter")

    raw_metadata = _parse_simple_yaml(match.group(1))
    missing = sorted(REQUIRED_FIELDS - raw_metadata.keys())
    if missing:
        raise FrontMatterError(f"missing required fields: {', '.join(missing)}")

    visibility = str(raw_metadata["visibility"])
    if visibility not in {"public", "private"}:
        raise FrontMatterError(f"invalid visibility: {visibility}")
    status = str(raw_metadata["status"])
    if status not in {"draft", "published"}:
        raise FrontMatterError(f"invalid status: {status}")

    metadata = DocumentMetadata(
        document_id=str(raw_metadata["document_id"]),
        title=str(raw_metadata["title"]),
        category=str(raw_metadata["category"]),
        project_id=_optional_str(raw_metadata.get("project_id")),
        visibility=visibility,
        status=status,
        updated_at=str(raw_metadata["updated_at"]),
        aliases=_parse_aliases(raw_metadata.get("aliases")),
    )
    return metadata, text[match.end() :]


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"null", "none", "~"}:
        return None
    return text or None


def _parse_aliases(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(
        alias.strip()
        for alias in re.split(r"[,，|]", str(value))
        if alias.strip()
    )


def _parse_simple_yaml(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition(":")
        if not separator:
            raise FrontMatterError(f"invalid front matter line: {line}")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result
