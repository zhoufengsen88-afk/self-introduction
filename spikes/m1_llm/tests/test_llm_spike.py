import unittest
from pathlib import Path

from spikes.m1_llm.context import build_oracle_context, chunk_lookup, load_public_chunks
from spikes.m1_llm.dataset import load_llm_cases
from spikes.m1_llm.evaluate import evaluate_stream
from spikes.m1_llm.fake_provider import FakeLLMProvider


ROOT = Path(__file__).resolve().parents[3]


class LlmSpikeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_llm_cases(ROOT / "evals/datasets/mvp-v1.jsonl")
        cls.chunks = load_public_chunks(ROOT / "knowledge")
        cls.chunks_by_id = chunk_lookup(cls.chunks)
        cls.provider = FakeLLMProvider()

    def test_loads_enabled_cases_and_disabled_refusal_cases(self):
        self.assertEqual(len([case for case in self.cases if case.enabled]), 16)
        self.assertEqual(len([case for case in self.cases if case.should_refuse]), 2)
        self.assertEqual(len(self.cases), 18)

    def test_fake_provider_answers_with_citations(self):
        case = next(item for item in self.cases if item.case_id == "challenge-003")
        context = build_oracle_context(case, self.chunks_by_id)
        events = list(self.provider.stream(case, context))
        row = evaluate_stream(case, events, context)
        self.assertTrue(row["refusal_ok"])
        self.assertTrue(row["required_ok"])
        self.assertTrue(row["forbidden_ok"])
        self.assertTrue(row["citation_ok"])

    def test_fake_provider_refuses_security_case_without_citations(self):
        case = next(item for item in self.cases if item.case_id == "security-001")
        context = build_oracle_context(case, self.chunks_by_id)
        events = list(self.provider.stream(case, context))
        row = evaluate_stream(case, events, context)
        self.assertTrue(row["refusal_ok"])
        self.assertTrue(row["citation_ok"])
        self.assertEqual(row["cited_chunk_ids"], [])


if __name__ == "__main__":
    unittest.main()
