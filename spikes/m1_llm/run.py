import argparse
import json
import os
import time
from pathlib import Path

from .context import build_oracle_context, chunk_lookup, load_public_chunks
from .dataset import load_llm_cases
from .evaluate import evaluate_stream, summarize
from .fake_provider import FakeLLMProvider
from .prompt import build_prompt


def available_real_provider_keys() -> dict:
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "dashscope": bool(os.environ.get("DASHSCOPE_API_KEY")),
        "zhipuai": bool(os.environ.get("ZHIPUAI_API_KEY") or os.environ.get("GLM_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the M1 LLM answer-contract spike")
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets/mvp-v1.jsonl"))
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument(
        "--enabled-only",
        action="store_true",
        help="exclude disabled refusal cases and evaluate enabled cases only",
    )
    parser.add_argument("--show-prompts", action="store_true")
    args = parser.parse_args()

    cases = load_llm_cases(args.dataset, include_refusal_cases=not args.enabled_only)
    if args.max_cases:
        cases = cases[: args.max_cases]
    chunks = load_public_chunks(args.knowledge, args.max_chars)
    chunks_by_id = chunk_lookup(chunks)
    provider = FakeLLMProvider()

    rows = []
    started = time.perf_counter()
    for case in cases:
        context = build_oracle_context(case, chunks_by_id)
        prompt = build_prompt(case, context)
        events = list(provider.stream(case, context))
        row = evaluate_stream(case, events, context)
        row["context_chunk_ids"] = [item.chunk_id for item in context]
        row["event_sequence"] = [event.event for event in events]
        if args.show_prompts:
            row["prompt"] = prompt
        rows.append(row)
    elapsed = time.perf_counter() - started

    output = {
        "environment": {
            "provider": provider.name,
            "case_count": len(cases),
            "enabled_case_count": sum(1 for case in cases if case.enabled),
            "refusal_case_count": sum(1 for case in cases if case.should_refuse),
            "chunk_count": len(chunks),
            "real_provider_keys_present": available_real_provider_keys(),
        },
        "summary": summarize(rows),
        "cost_estimate": {
            "fake_provider_cost_usd": 0.0,
            "real_provider_cost_usd": None,
            "notes": "No real provider was called in this offline baseline.",
        },
        "latency": {
            "total_seconds": round(elapsed, 4),
            "mean_case_ms": round((elapsed / len(cases) * 1000) if cases else 0.0, 4),
        },
        "cases": rows,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
