"""搜索统计与热门车型。

热门口径：按 queryCarPrice 的累计搜索次数倒序取前 N；
不足 N 个时用示例库（品牌+车型）补齐，保证首页始终有可点选的快捷入口。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SearchStat, utcnow
from app.services.sample_cars import all_samples

HOT_LIMIT = 5
MAX_KEYWORD_LEN = 64


def normalize_keyword(keyword: str | None) -> str:
    """合并空白并截断；空串返回空。"""
    return " ".join((keyword or "").split())[:MAX_KEYWORD_LEN]


def default_keywords() -> list[str]:
    """默认热门车型：取自内置示例库，保证与演示数据一致。"""
    return [f"{brand} {model}" for brand, model, *_ in all_samples()]


def record_search(db: Session, keyword: str | None) -> None:
    """记录一次搜索；长度过短的关键词不统计。"""
    kw = normalize_keyword(keyword)
    if len(kw) < 2:
        return

    stat = db.get(SearchStat, kw)
    if stat is None:
        db.add(SearchStat(keyword=kw, count=1, last_searched_at=utcnow()))
    else:
        stat.count += 1
        stat.last_searched_at = utcnow()
    db.commit()


def hot_keywords(db: Session, limit: int = HOT_LIMIT) -> list[str]:
    """按搜索量取前 limit 个关键词，不足用默认车型补齐。"""
    rows = db.scalars(
        select(SearchStat)
        .where(SearchStat.count > 0)
        .order_by(SearchStat.count.desc(), SearchStat.last_searched_at.desc())
        .limit(limit)
    ).all()
    items = [row.keyword for row in rows]

    for keyword in default_keywords():
        if len(items) >= limit:
            break
        if keyword not in items:
            items.append(keyword)

    return items[:limit]
