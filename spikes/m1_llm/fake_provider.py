from typing import Iterable, Sequence

from .contracts import Citation, Evidence, LlmAnswer, LlmEvaluationCase, StreamEvent


class FakeLLMProvider:
    name = "fake-llm"

    def generate(self, case: LlmEvaluationCase, context: Sequence[Evidence]) -> LlmAnswer:
        if case.should_refuse:
            reason = case.refusal_reason or "restricted_or_insufficient_evidence"
            return LlmAnswer(
                answer=f"这个问题我不能回答，因为它涉及{reason}，或超出了当前公开知识库允许回答的范围。",
                citations=(),
                refused=True,
                refusal_reason=reason,
            )

        if not context:
            return LlmAnswer(
                answer="当前公开知识库里没有足够证据回答这个问题，我不能凭空补充。",
                citations=(),
                refused=True,
                refusal_reason="insufficient_evidence",
            )

        facts = list(case.required_facts)
        if facts:
            fact_text = "、".join(facts)
            answer = f"根据当前公开资料，我可以这样回答：{fact_text}。"
        else:
            answer = "根据当前公开资料，我可以回答这个问题，但需要保持在证据范围内。"

        if len(context) == 1:
            answer += f" 主要证据来自 {context[0].chunk_id}。"
        else:
            answer += " 这些结论分别由以下公开证据支持：" + "、".join(
                item.chunk_id for item in context
            ) + "。"

        citations = tuple(
            Citation(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                document_title=item.document_title,
            )
            for item in context
        )
        return LlmAnswer(answer=answer, citations=citations)

    def stream(self, case: LlmEvaluationCase, context: Sequence[Evidence]) -> Iterable[StreamEvent]:
        answer = self.generate(case, context)
        step = 24
        for index in range(0, len(answer.answer), step):
            yield StreamEvent(
                event="delta",
                data={"content": answer.answer[index : index + step]},
            )
        yield StreamEvent(
            event="done",
            data={
                "finish_reason": "stop",
                "refused": answer.refused,
                "refusal_reason": answer.refusal_reason,
                "citations": [
                    {
                        "chunk_id": citation.chunk_id,
                        "document_id": citation.document_id,
                        "document_title": citation.document_title,
                    }
                    for citation in answer.citations
                ],
            },
        )
