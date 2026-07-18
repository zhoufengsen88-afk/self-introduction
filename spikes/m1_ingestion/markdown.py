import re
from typing import List, Tuple

from .models import Section


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _is_matching_fence(line: str, marker: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith(marker[0] * len(marker))


def split_sections(markdown: str, document_title: str = "") -> List[Section]:
    """Split Markdown into sections keyed by semantic heading paths.

    The first H1 is treated as the document root title even when it differs
    from the shorter front matter display title.
    """
    sections: List[Section] = []
    heading_stack: List[Tuple[int, str]] = []
    current_lines: List[str] = []
    current_path: Tuple[str, ...] = ()
    fence_marker = ""
    ignored_root_h1 = False
    seen_heading = False

    def flush() -> None:
        nonlocal current_lines
        blocks = _split_blocks(current_lines)
        if blocks:
            sections.append(Section(current_path, tuple(blocks)))
        current_lines = []

    for line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        fence_match = FENCE_RE.match(line)
        if fence_marker:
            current_lines.append(line.rstrip())
            if fence_match and _is_matching_fence(line, fence_marker):
                fence_marker = ""
            continue
        if fence_match:
            fence_marker = fence_match.group(1)
            current_lines.append(line.rstrip())
            continue

        heading_match = HEADING_RE.match(line)
        if not heading_match:
            current_lines.append(line.rstrip())
            continue

        level = len(heading_match.group(1))
        title = heading_match.group(2).strip()
        if level == 1 and not ignored_root_h1 and not seen_heading:
            flush()
            ignored_root_h1 = True
            seen_heading = True
            heading_stack = []
            current_path = ()
            continue

        flush()
        seen_heading = True
        heading_stack = [(old_level, old_title) for old_level, old_title in heading_stack if old_level < level]
        heading_stack.append((level, title))
        current_path = tuple(item[1] for item in heading_stack)

    flush()
    return sections


def _split_blocks(lines: List[str]) -> List[str]:
    blocks: List[str] = []
    current: List[str] = []
    fence_marker = ""

    def flush() -> None:
        nonlocal current
        value = "\n".join(current).strip()
        if value:
            blocks.append(value)
        current = []

    for line in lines:
        fence_match = FENCE_RE.match(line)
        if fence_marker:
            current.append(line)
            if fence_match and _is_matching_fence(line, fence_marker):
                fence_marker = ""
                flush()
            continue
        if fence_match:
            flush()
            fence_marker = fence_match.group(1)
            current.append(line)
        elif not line.strip():
            flush()
        else:
            current.append(line)
    flush()
    return blocks
