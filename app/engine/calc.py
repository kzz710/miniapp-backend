"""费用计算引擎（纯函数）。

公式来源：技术方案第 8 节。
- 落地价 = 裸车价 + 购置税 + 保险 + 上牌杂费
- 购置税 = 裸车价 / 11.3（不含税价 × 10%，含 13% 增值税近似）；电车（ev）按现行政策减半
- 保险 ≈ 裸车价 × 5%
- 上牌/服务费 ≈ 0.15 万元（固定估算）
- 分期月供：等额本息  M = P·r·(1+r)^n / ((1+r)^n − 1)
"""
from typing import Literal

TAX_DIVISOR = 11.3
INSURANCE_RATE = 0.05
MISC_FEE = 0.15  # 万元
EV_PURCHASE_TAX_FACTOR = 0.5  # 电车购置税减半（现行政策）


def calc_landed_price(price: float, energy_type: str = "gas") -> dict:
    """裸车价 -> 购置税/保险/杂费/落地总价（万元）。

    电车（ev）适用购置税减半政策；购置税原价 = 裸车价 / TAX_DIVISOR。
    """
    halved = energy_type == "ev"
    purchase_tax = price / TAX_DIVISOR * (EV_PURCHASE_TAX_FACTOR if halved else 1.0)
    insurance = price * INSURANCE_RATE
    misc_fee = MISC_FEE
    return {
        "purchase_tax": purchase_tax,
        "purchase_tax_halved": halved,
        "insurance": insurance,
        "misc_fee": misc_fee,
        "landed_price": price + purchase_tax + insurance + misc_fee,
    }


def calc_loan(price: float, down_payment_ratio: float, months: int, annual_rate: float) -> dict:
    """等额本息分期明细（万元）。"""
    loan_amount = price * (1 - down_payment_ratio)
    down_payment = price * down_payment_ratio
    r = annual_rate / 12
    if r == 0:
        monthly_payment = loan_amount / months
    else:
        pow_ = (1 + r) ** months
        monthly_payment = loan_amount * r * pow_ / (pow_ - 1)
    total_interest = monthly_payment * months - loan_amount
    return {
        "loan_amount": loan_amount,
        "down_payment": down_payment,
        "monthly_payment": monthly_payment,
        "total_interest": total_interest,
    }


def calc_full_plan(price: float, energy_type: str = "gas") -> dict:
    """全款方案。"""
    land = calc_landed_price(price, energy_type)
    land.update(
        mode="full",
        down_payment=land["landed_price"],
        loan_amount=0.0,
        monthly_payment=0.0,
        total_interest=0.0,
    )
    return land


def calc_loan_plan(
    price: float,
    down_payment_ratio: float,
    months: int,
    annual_rate: float,
    energy_type: str = "gas",
) -> dict:
    """分期方案。"""
    land = calc_landed_price(price, energy_type)
    loan = calc_loan(price, down_payment_ratio, months, annual_rate)
    land.update(mode="loan", **loan)
    return land


def run_plan(
    price: float,
    mode: Literal["full", "loan"],
    down_payment_ratio: float = 0.3,
    months: int = 36,
    annual_rate: float = 0.045,
    energy_type: str = "gas",
) -> dict:
    """组合：返回一个方案的完整明细 dict。"""
    if mode == "loan":
        return calc_loan_plan(price, down_payment_ratio, months, annual_rate, energy_type)
    return calc_full_plan(price, energy_type)


def calc_energy_cost(
    energy_type: str,
    fuel_consumption: float = 0.0,
    power_consumption: float = 0.0,
    monthly_km: int = 1000,
    fuel_price: float = 7.5,
    electricity_price: float = 0.6,
) -> dict:
    """按月行驶里程估算油费 / 电费（返回单位：万元）。

    - gas / hybrid：产生油费（百公里油耗 × 油价）
    - ev：产生电费（百公里电耗 × 电价）
    - 换算：元 ÷ 10000 = 万元
    """
    factor = monthly_km / 100.0  # 每百公里倍数
    fuel_yuan = 0.0
    elec_yuan = 0.0
    if energy_type in ("gas", "hybrid"):
        fuel_yuan = fuel_consumption * fuel_price * factor
    if energy_type == "ev":
        elec_yuan = power_consumption * electricity_price * factor
    return {
        "fuel_cost_month": round(fuel_yuan / 10000.0, 4),
        "electricity_cost_month": round(elec_yuan / 10000.0, 4),
        "energy_cost_month": round((fuel_yuan + elec_yuan) / 10000.0, 4),
    }
