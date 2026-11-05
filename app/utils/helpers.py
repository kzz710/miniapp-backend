"""辅助函数：时间、slug。"""
from datetime import datetime, timedelta, timezone

# 业务时区（北京时间），用于「每日限额」等按本地日计算的口径
CN_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    """当前时间 ISO8601（含时区）。"""
    return datetime.now(timezone.utc).astimezone().isoformat()


def start_of_today_cn_utc() -> datetime:
    """北京时间「今天 00:00」对应的 UTC naive 时间。

    数据库统一存 UTC naive，因此按北京时间取日界后再转 UTC，避免限额在北京时间早上 8 点重置。
    """
    now_cn = datetime.now(CN_TZ)
    start_cn = now_cn.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_cn.astimezone(timezone.utc).replace(tzinfo=None)


def slugify(text: str) -> str:
    """把任意车型文本转成简单 id（小写、去空格、截断）。"""
    s = "".join(ch for ch in text if ch.isalnum() or ch in (" ", "-"))
    s = s.strip().lower().replace(" ", "-")
    return s[:64] or "unknown"
