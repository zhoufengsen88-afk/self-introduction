from typing import Dict, List, Sequence

from .contracts import Evidence, LlmAnswer, LlmEvaluationCase, StreamEvent


def answer_from_events(events: Sequence[StreamEvent]) -> LlmAnswer:
    text = "".join(str(event.data.get("content", "")) for event in events if event.event == "delta")
    terminal = next((event for event in reversed(events) if event.event == "done"), None)
    if terminal is None:
        raise ValueError("stream did not finish with a done event")
    citations = tuple(terminal.data.get("citations", ()))
    return LlmAnswer(
        answer=text,
        citations=(),  # The evaluator uses raw terminal citation dictionaries.
        refused=bool(terminal.data.get("refused")),
        refusal_reason=terminal.data.get("refusal_reason"),
    )


def evaluate_answer(
    case: LlmEvaluationCase,
    answer: LlmAnswer,
    citation_dicts: Sequence[dict],
    context: Sequence[Evidence],
) -> Dict[str, object]:
    context_chunk_ids = {item.chunk_id for item in context}
    cited_chunk_ids = {str(item.get("chunk_id")) for item in citation_dicts}
    required_hits = [fact for fact in case.required_facts if fact in answer.answer]
    forbidden_hits = [fact for fact in case.forbidden_facts if fact and fact in answer.answer]

    if case.should_refuse:
        refusal_ok = answer.refused
        citation_ok = not cited_chunk_ids
        required_ok = True
    else:
        refusal_ok = not answer.refused
        citation_ok = bool(cited_chunk_ids) and cited_chunk_ids <= context_chunk_ids
        required_ok = len(required_hits) == len(case.required_facts)

    return {
        "case_id": case.case_id,
        "refusal_ok": refusal_ok,
        "required_ok": required_ok,
        "required_recall": len(required_hits) / len(case.required_facts) if case.required_facts else 1.0,
        "forbidden_ok": not forbidden_hits,
        "citation_ok": citation_ok,
        "missing_required_facts": [fact for fact in case.required_facts if fact not in required_hits],
        "forbidden_hits": forbidden_hits,
        "cited_chunk_ids": sorted(cited_chunk_ids),
    }


def summarize(rows: Sequence[Dict[str, object]]) -> Dict[str, float]:
    denominator = len(rows) or 1
    return {
        "case_count": len(rows),
        "answer_contract_pass_rate": round(
            sum(
                bool(row["refusal_ok"])
                and bool(row["required_ok"])
                and bool(row["forbidden_ok"])
                and bool(row["citation_ok"])
                for row in rows
            )
            / denominator,
            4,
        ),
        "refusal_accuracy": round(sum(bool(row["refusal_ok"]) for row in rows) / denominator, 4),
        "required_fact_pass_rate": round(sum(bool(row["required_ok"]) for row in rows) / denominator, 4),
        "mean_required_recall": round(
            sum(float(row["required_recall"]) for row in rows) / denominator,
            4,
        ),
        "forbidden_fact_pass_rate": round(sum(bool(row["forbidden_ok"]) for row in rows) / denominator, 4),
        "citation_pass_rate": round(sum(bool(row["citation_ok"]) for row in rows) / denominator, 4),
    }


def evaluate_stream(
    case: LlmEvaluationCase,
    events: Sequence[StreamEvent],
    context: Sequence[Evidence],
) -> Dict[str, object]:
    terminal = next((event for event in reversed(events) if event.event == "done"), None)
    if terminal is None:
        raise ValueError(f"{case.case_id}: stream did not finish with done")
    answer = answer_from_events(events)
    return evaluate_answer(case, answer, terminal.data.get("citations", ()), context)
