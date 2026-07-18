import datetime as dt
import re
from typing import Dict, Optional, Tuple

from .models import DocumentMetadata


class FrontMatterError(ValueError):
    pass


REQUIRED_FIELDS = {
    "document_id",
    "title",
    "category",
    "project_id",
    "visibility",
    "status",
    "updated_at",
}
VALID_CATEGORIES = {"profile", "skills", "resume", "project"}
VALID_VISIBILITIES = {"public", "private"}
VALID_STATUSES = {"draft", "published"}
KEY_VALUE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")


def _parse_scalar(raw: str) -> Optional[str]:
    value = raw.strip()
    if value in {"null", "~"}:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_front_matter(text: str) -> Tuple[DocumentMetadata, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        raise FrontMatterError("document must start with a front matter delimiter")

    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise FrontMatterError("front matter closing delimiter is missing") from exc

    values: Dict[str, Optional[str]] = {}
    for line_number, line in enumerate(lines[1:closing], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = KEY_VALUE_RE.match(line)
        if not match:
            raise FrontMatterError(f"unsupported front matter syntax at line {line_number}")
        key, raw_value = match.groups()
        if key in values:
            raise FrontMatterError(f"duplicate front matter field: {key}")
        values[key] = _parse_scalar(raw_value or "")

    missing = REQUIRED_FIELDS - values.keys()
    if missing:
        raise FrontMatterError(f"missing required fields: {', '.join(sorted(missing))}")

    def required_string(key: str) -> str:
        value = values[key]
        if value is None or not value.strip():
            raise FrontMatterError(f"{key} must be a non-empty string")
        return value.strip()

    document_id = required_string("document_id")
    title = required_string("title")
    category = required_string("category")
    visibility = required_string("visibility")
    status = required_string("status")
    updated_at = required_string("updated_at")
    project_id = values["project_id"]
    project_id = project_id.strip() if project_id else None

    if category not in VALID_CATEGORIES:
        raise FrontMatterError(f"invalid category: {category}")
    if visibility not in VALID_VISIBILITIES:
        raise FrontMatterError(f"invalid visibility: {visibility}")
    if status not in VALID_STATUSES:
        raise FrontMatterError(f"invalid status: {status}")
    if category == "project" and not project_id:
        raise FrontMatterError("project documents require project_id")
    try:
        dt.date.fromisoformat(updated_at)
    except ValueError as exc:
        raise FrontMatterError("updated_at must use YYYY-MM-DD") from exc

    metadata = DocumentMetadata(
        document_id=document_id,
        title=title,
        category=category,
        project_id=project_id,
        visibility=visibility,
        status=status,
        updated_at=updated_at,
    )
    body = "\n".join(lines[closing + 1 :]).strip() + "\n"
    return metadata, body
