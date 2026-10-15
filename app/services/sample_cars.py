"""内置示例车型库：作为实时检索失败时的兜底，保证 MVP 全流程跑通。

生产环境应替换为实时检索结果；示例库仅用于演示与可用性兜底。
价格单位：万元。以下为近似参考值，非实时报价。
"""
from typing import List, Optional

from app.types import CarPrice
from app.utils.helpers import now_iso, slugify

# 每个元素：(品牌, 车型, 配置, 指导价, 参考优惠价, 能源类型, 百公里油耗L, 百公里电耗kWh)
# 能源类型：gas=油车, ev=电车, hybrid=混动（混动按油费估算）
_SAMPLE = [
    ("比亚迪", "海豹", "650 长续航版", 18.98, 17.50, "ev", 0.0, 13.0),
    ("比亚迪", "秦PLUS", "DM-i 55KM 领先型", 10.58, 9.58, "hybrid", 4.6, 0.0),
    ("特斯拉", "Model 3", "后轮驱动版", 23.55, 23.55, "ev", 0.0, 12.5),
    ("丰田", "凯美瑞", "2.0L 豪华版", 19.18, 17.18, "gas", 6.5, 0.0),
    ("本田", "雅阁", "260TURBO 舒适版", 19.78, 17.48, "gas", 7.0, 0.0),
    ("理想", "L6", "Pro", 24.98, 24.98, "ev", 0.0, 19.0),
    ("小米", "SU7", "标准版", 21.59, 21.59, "ev", 0.0, 13.5),
]


def all_samples() -> List[tuple]:
    return list(_SAMPLE)


def find_sample(keyword: str) -> Optional[CarPrice]:
    """按关键词（品牌或车型子串）模糊匹配示例库。"""
    if not keyword:
        return None
    for brand, model, config, guide, discount, energy_type, fuel_c, power_c in _SAMPLE:
        if brand in keyword or model in keyword:
            return CarPrice(
                car_id=slugify(f"{brand}-{model}-{config}"),
                brand=brand,
                model=model,
                config=config,
                guide_price=guide,
                ref_discount_price=discount,
                energy_type=energy_type,
                fuel_consumption=fuel_c,
                power_consumption=power_c,
                source="内置示例库（参考值）",
                fetched_at=now_iso(),
            )
    return None
