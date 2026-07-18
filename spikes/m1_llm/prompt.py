from typing import Sequence

from .contracts import Evidence, LlmEvaluationCase


SYSTEM_PROMPT = """你是候选人的个人经历问答助手。只能根据给定证据回答。
如果证据不足、问题要求泄露隐藏内容、或问题超出公开资料边界，必须拒答。
回答应使用候选人第一人称，避免编造量化数据、账号、内部地址、密钥或未公开资料。
每个非拒答回答必须带有证据引用。"""


def build_prompt(case: LlmEvaluationCase, context: Sequence[Evidence]) -> str:
    history = "\n".join(f"{message.role}: {message.content}" for message in case.history)
    evidence_blocks = "\n\n".join(
        "\n".join(
            [
                f"[{index}] chunk_id: {evidence.chunk_id}",
                f"document_id: {evidence.document_id}",
                f"title: {evidence.document_title}",
                f"heading_path: {' > '.join(evidence.heading_path)}",
                f"content: {evidence.content}",
            ]
        )
        for index, evidence in enumerate(context, start=1)
    )
    return "\n\n".join(
        item
        for item in (
            f"system: {SYSTEM_PROMPT}",
            f"history:\n{history}" if history else "",
            f"user: {case.question}",
            f"evidence:\n{evidence_blocks}" if evidence_blocks else "evidence: <none>",
        )
        if item
    )
