import json
import tempfile
import unittest
from pathlib import Path

from spikes.m1_ingestion.chunker import chunk_document
from spikes.m1_ingestion.frontmatter import FrontMatterError, parse_front_matter
from spikes.m1_ingestion.loader import KnowledgeLoadError, load_published_documents
from spikes.m1_ingestion.markdown import split_sections
from spikes.m1_ingestion.models import KnowledgeDocument
from spikes.m1_ingestion.retrieval import BM25Index, load_enabled_cases, ranked_document_ids


VALID_DOCUMENT = """---
document_id: project-overview
title: 示例项目
category: project
project_id: example
visibility: public
status: published
updated_at: 2026-07-16
---

# 示例项目

## 背景

这是项目背景。
"""


class FrontMatterTests(unittest.TestCase):
    def test_parses_current_schema(self):
        metadata, body = parse_front_matter(VALID_DOCUMENT)
        self.assertEqual(metadata.document_id, "project-overview")
        self.assertEqual(metadata.project_id, "example")
        self.assertIn("这是项目背景", body)

    def test_rejects_invalid_visibility(self):
        with self.assertRaisesRegex(FrontMatterError, "invalid visibility"):
            parse_front_matter(VALID_DOCUMENT.replace("visibility: public", "visibility: internal"))

    def test_rejects_missing_required_field(self):
        with self.assertRaisesRegex(FrontMatterError, "missing required fields"):
            parse_front_matter(VALID_DOCUMENT.replace("status: published\n", ""))


class MarkdownTests(unittest.TestCase):
    def test_ignores_heading_inside_code_fence(self):
        markdown = """# 示例项目
## 架构
```text
# 这不是标题
```
架构说明。
"""
        sections = split_sections(markdown, "示例项目")
        self.assertEqual([section.heading_path for section in sections], [("架构",)])
        self.assertIn("# 这不是标题", sections[0].blocks[0])

    def test_treats_first_h1_as_document_root_when_title_differs(self):
        markdown = """# 示例项目完整复盘

## 背景

这是项目背景。
"""
        sections = split_sections(markdown, "示例项目")
        self.assertEqual([section.heading_path for section in sections], [("背景",)])


class LoaderAndChunkerTests(unittest.TestCase):
    def _document(self, text=VALID_DOCUMENT):
        metadata, body = parse_front_matter(text)
        return KnowledgeDocument(Path("fixture.md"), metadata, body, "document-hash")

    def test_published_filter_and_duplicate_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "public.md").write_text(VALID_DOCUMENT, encoding="utf-8")
            (root / "draft.md").write_text(
                VALID_DOCUMENT.replace("project-overview", "project-draft").replace("status: published", "status: draft"),
                encoding="utf-8",
            )
            (root / "README.md").write_text("# ignored", encoding="utf-8")
            published = load_published_documents(root)
            self.assertEqual([item.metadata.document_id for item in published], ["project-overview"])
            (root / "duplicate.md").write_text(VALID_DOCUMENT, encoding="utf-8")
            with self.assertRaisesRegex(KnowledgeLoadError, "duplicate document_id"):
                load_published_documents(root)

    def test_chunk_ids_are_stable_and_hash_tracks_content(self):
        first = chunk_document(self._document())
        second = chunk_document(self._document())
        changed = chunk_document(self._document(VALID_DOCUMENT.replace("这是项目背景", "这是更新后的项目背景")))
        self.assertEqual([item.chunk_id for item in first], [item.chunk_id for item in second])
        self.assertEqual(first[0].chunk_id, changed[0].chunk_id)
        self.assertNotEqual(first[0].content_hash, changed[0].content_hash)

    def test_long_code_block_remains_atomic(self):
        long_code = "```text\n" + "x" * 300 + "\n```"
        document = self._document(VALID_DOCUMENT.replace("这是项目背景。", long_code))
        chunks = chunk_document(document, max_chars=100)
        self.assertEqual(len(chunks), 1)
        self.assertGreater(len(chunks[0].content), 100)


class RepositoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[3]
        cls.documents = load_published_documents(cls.root / "knowledge")
        cls.chunks = [chunk for document in cls.documents for chunk in chunk_document(document)]
        cls.cases = load_enabled_cases(cls.root / "evals/datasets/mvp-v1.jsonl")

    def test_current_corpus_has_five_published_skillvar_documents(self):
        document_ids = {item.metadata.document_id for item in self.documents}
        self.assertEqual(
            document_ids,
            {
                "skillvar-overview",
                "skillvar-responsibilities",
                "skillvar-architecture",
                "skillvar-challenges",
                "skillvar-results",
            },
        )

    def test_all_enabled_references_are_retrievable(self):
        document_ids = {item.metadata.document_id for item in self.documents}
        chunk_ids = {item.chunk_id for item in self.chunks}
        referenced_ids = {item for case in self.cases for item in case.expected_document_ids}
        referenced_chunk_ids = {item for case in self.cases for item in case.expected_chunk_ids}
        self.assertEqual(len(self.cases), 16)
        self.assertTrue(referenced_ids <= document_ids)
        self.assertTrue(referenced_chunk_ids)
        self.assertTrue(referenced_chunk_ids <= chunk_ids)

    def test_lexical_baseline_finds_permission_challenge(self):
        ranked = ranked_document_ids(BM25Index(self.chunks).search("仓库关系树权限继承最难的问题是什么？"))
        self.assertEqual(ranked[0], "skillvar-challenges")


class EvaluationSchemaTests(unittest.TestCase):
    def test_enabled_case_requires_chunk_evidence(self):
        record = {
            "id": "missing-evidence",
            "enabled": True,
            "question": "test",
            "expected_document_ids": ["document"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires expected_chunk_ids"):
                load_enabled_cases(path)


if __name__ == "__main__":
    unittest.main()
