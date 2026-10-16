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


def _extract_json_substring(text: str) -> Optional[str]:
    """从可能夹带前言/解释文字的文本中，抽取第一个完整的 JSON 对象或数组。

    用括号配对扫描（正确处理嵌套与字符串内的括号），避免正则误判。
    找不到则返回 None。
    """
    open_ch = close_ch = None
    start = None
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            open_ch, close_ch = ch, "}" if ch == "{" else "]"
            break
    if start is None:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_json_strict(raw: str) -> Optional[dict]:
    """尽力解析 JSON，失败返回 None。

    容错增强：
    - 去除 ```json ... ``` 代码块包裹；
    - 模型若在 JSON 前后夹带解释文字（如"以下是结果：{...}"），
      自动抽取第一个完整 JSON 对象/数组再解析。
    """
    import json

    if not raw:
        return None
    raw = raw.strip()

    # 去掉可能存在的代码块围栏
    if "```" in raw:
        raw = raw.split("```", 1)[-1]
        if "```" in raw:
            raw = raw.split("```", 1)[0]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except Exception:
        sub = _extract_json_substring(raw)
        if sub:
            try:
                return json.loads(sub)
            except Exception:
                return None
        return None
