"""数值 / 模型输出校验，异常即兜底。"""
from typing import Optional

from app.types import CarPrice


def validate_price(car: Optional[CarPrice]) -> bool:
    """校验抽取出的价格是否合理：非负、且在合理区间（1~1000 万）。"""
    if car is None:
        return False
    try:
        for v in (car.guide_price, car.ref_discount_price):
            if not isinstance(v, (int, float)) or v < 1 or v > 1000:
                return False
        if car.ref_discount_price > car.guide_price * 1.2:
            # 优惠价不应高于指导价太多
            return False
        return True
    except Exception:
        return False


def parse_json_strict(raw: str) -> Optional[dict]:
    """尽力解析 JSON，失败返回 None。"""
    import json

    try:
        return json.loads(raw)
    except Exception:
        return None
