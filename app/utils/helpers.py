"""辅助函数：时间、slug。"""
from datetime import datetime, timezone


def now_iso() -> str:
    """当前时间 ISO8601（含时区）。"""
    return datetime.now(timezone.utc).astimezone().isoformat()


def slugify(text: str) -> str:
    """把任意车型文本转成简单 id（小写、去空格、截断）。"""
    s = "".join(ch for ch in text if ch.isalnum() or ch in (" ", "-"))
    s = s.strip().lower().replace(" ", "-")
    return s[:64] or "unknown"
