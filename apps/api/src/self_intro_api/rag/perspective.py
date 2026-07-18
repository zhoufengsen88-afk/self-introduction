FIRST_PERSON_SIGNALS = (
    "第一人称",
    "以我",
    "用我的口吻",
    "候选人口吻",
    "自我介绍",
    "介绍自己",
    "口述",
    "口述稿",
    "面试稿",
    "面试话术",
    "我该怎么说",
    "帮我写",
    "帮我组织",
    "替我",
    "代我",
)

FIRST_PERSON_ENGLISH_SIGNALS = (
    "first person",
    "as me",
    "in my voice",
    "self introduction",
    "self-introduction",
    "interview script",
)


def wants_first_person_response(question: str) -> bool:
    normalized = question.lower()
    return any(signal in question for signal in FIRST_PERSON_SIGNALS) or any(
        signal in normalized for signal in FIRST_PERSON_ENGLISH_SIGNALS
    )
