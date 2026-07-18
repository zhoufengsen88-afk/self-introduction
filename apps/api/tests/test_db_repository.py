from self_intro_api.knowledge.db_repository import (
    deserialize_heading_path,
    serialize_heading_path,
)


def test_heading_path_round_trip() -> None:
    heading_path = ("已确认的个人实现范围", "MCP 与 CLI")

    encoded = serialize_heading_path(heading_path)

    assert deserialize_heading_path(encoded) == heading_path


def test_heading_path_legacy_fallback() -> None:
    assert deserialize_heading_path("A > B > C") == ("A", "B", "C")
