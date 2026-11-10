"""审批标签白名单。

审核要求：审批不接收用户自由文本，只允许从预设标签中选择，
服务端负责校验并转换为展示文案，避免形成 UGC 内容。
"""
REVIEW_TAGS = {
    "high_payment": "月供偏高",
    "low_down": "首付偏低",
    "high_cost": "用车成本高",
    "save_more": "建议再攒几个月",
    "negotiate": "价格还能谈",
    "better_choice": "同价位有更好选择",
    "good_commute": "适合通勤",
}

MAX_REVIEW_TAGS = 3
TAG_TEXT_TO_KEY = {text: key for key, text in REVIEW_TAGS.items()}


def normalize_tags(raw: list[str] | None) -> list[str]:
    """过滤非法标签、去重并限制数量（保持传入顺序）。"""
    out: list[str] = []
    for tag in raw or []:
        if tag in REVIEW_TAGS and tag not in out:
            out.append(tag)
    return out[:MAX_REVIEW_TAGS]


def tags_to_text(tags: list[str]) -> str:
    return "、".join(REVIEW_TAGS[tag] for tag in tags if tag in REVIEW_TAGS)


def parse_tags(comment: str | None) -> list[str]:
    """从存量 comment 中解析出标签；历史自由文本解析不到则为空。"""
    parts = [part.strip() for part in (comment or "").split("、") if part.strip()]
    return [TAG_TEXT_TO_KEY[part] for part in parts if part in TAG_TEXT_TO_KEY][:MAX_REVIEW_TAGS]
