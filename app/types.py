"""Pydantic 数据模型：对外接口契约。"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CarPrice(BaseModel):
    """车型价格（单位：万元）。"""

    car_id: str = Field(..., description="车型唯一标识")
    brand: str = Field(..., description="品牌")
    model: str = Field(..., description="车型")
    config: str = Field(..., description="配置")
    guide_price: float = Field(..., description="指导价（万元）")
    ref_discount_price: float = Field(..., description="参考优惠价（万元）")
    energy_type: str = Field("gas", description="能源类型：gas=油车, ev=电车, hybrid=混动")
    fuel_consumption: float = Field(0.0, description="百公里油耗（L/100km），油车/混动填")
    power_consumption: float = Field(0.0, description="百公里电耗（kWh/100km），电车/混动填")
    source: str = Field(..., description="价格来源 URL / 渠道")
    fetched_at: str = Field(..., description="抓取时间 ISO8601")


class CalcParams(BaseModel):
    """费用测算 + 可负担性评估入参。"""

    price: float = Field(..., gt=0, description="裸车价（万元），通常取参考优惠价")
    mode: Literal["full", "loan"] = Field(..., description="full=全款，loan=分期")
    down_payment_ratio: float = Field(0.3, ge=0, le=1, description="首付比例，默认 0.3")
    months: int = Field(36, gt=0, description="分期期数，12/24/36/60")
    annual_rate: float = Field(0.045, ge=0, description="年化利率，默认 4.5%")
    income: float = Field(..., ge=0, description="月收入（万元）")
    monthly_expense: float = Field(..., ge=0, description="月固定支出（万元）")
    savings: float = Field(..., ge=0, description="可用储蓄（万元）")
    safe_ratio: float = Field(0.3, gt=0, le=1, description="安全月供占可支配收入比例")
    energy_type: str = Field("gas", description="能源类型：gas=油车, ev=电车, hybrid=混动")
    fuel_consumption: float = Field(0.0, description="百公里油耗（L/100km）")
    power_consumption: float = Field(0.0, description="百公里电耗（kWh/100km）")
    monthly_km: int = Field(1000, gt=0, description="每月行驶里程（km），默认 1000")
    fuel_price: float = Field(7.5, gt=0, description="油价（元/L），默认 7.5")
    electricity_price: float = Field(0.6, gt=0, description="电价（元/kWh），默认 0.6（家用充电）")


class CalcResult(BaseModel):
    """测算结果。"""

    mode: Literal["full", "loan"]
    landed_price: float = Field(..., description="落地总价（万元）")
    purchase_tax: float = Field(..., description="购置税（万元）")
    purchase_tax_halved: bool = Field(False, description="购置税是否减半（电车现行政策）")
    insurance: float = Field(..., description="保险（万元）")
    misc_fee: float = Field(..., description="上牌/服务费（万元）")
    down_payment: float = Field(..., description="首付（万元）")
    loan_amount: float = Field(..., description="贷款额（万元）")
    monthly_payment: float = Field(..., description="月供（万元）")
    total_interest: float = Field(..., description="总利息（万元）")
    disposable_income: float = Field(..., description="可支配收入 D（万元，已扣除能源费）")
    safe_monthly_payment: float = Field(..., description="安全月供线 S（万元）")
    energy_type: str = Field("gas", description="能源类型：gas=油车, ev=电车, hybrid=混动")
    fuel_cost_month: float = Field(0.0, description="每月油费（万元）")
    electricity_cost_month: float = Field(0.0, description="每月电费（万元）")
    energy_cost_month: float = Field(0.0, description="每月能源费合计（万元）")
    monthly_km: int = Field(1000, description="每月行驶里程（km）")
    verdict: Literal["buy", "consider", "avoid"]
    verdict_text: str = Field(..., description="买买买 / 理性考虑 / 买个 der")
    reason: str = Field(..., description="结论文案")


class CarPriceResult(BaseModel):
    """车价查询返回，含来源与兜底标记。

    data   : 默认推荐版本（取 options[0]），前端可直接使用；
    options: 该车型在售的全部版本（用户可逐个选择）。data 恒等于 options[0]。
    """

    data: Optional[CarPrice] = None
    options: list[CarPrice] = Field(default_factory=list, description="该车型所有版本（含 data）")
    is_reference: bool = Field(False, description="是否为参考值（示例库兜底时为真）")
    source: Literal["cache", "live", "sample", "none"]
    note: Optional[str] = None
