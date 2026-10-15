"""真实联调脚本：验证豆包(火山方舟) 实时联网检索 + 价格抽取全链路。

运行：
  cd D:/workspace/myself/miniapp-backend
  .venv/Scripts/python.exe app/tests/integration_real.py
"""
import asyncio
import json

from app import config
from app.services.llm import fetch_live_prices
from app.services.car_price import get_car_price
from app.engine import run_plan
from app.types import CalcParams


def mask(s: str, n: int = 6) -> str:
    if not s:
        return "<空>"
    return s[:n] + "…" + s[-n:] if len(s) > 2 * n else "***"


async def main() -> None:
    print("=" * 60)
    print("联调环境检查")
    print("=" * 60)
    print(f"LLM_PROVIDER      : {config.LLM_PROVIDER}")
    print(f"DOUBAO_API_KEY    : {mask(config.DOUBAO_API_KEY)}")
    print(f"DOUBAO_MODEL      : {config.DOUBAO_MODEL}")
    print(f"DOUBAO_BASE_URL   : {config.DOUBAO_BASE_URL}")
    print(f"live_mode()       : {config.live_mode()}")
    print(f"llm_label()       : {config.llm_label()}")

    if not config.live_mode():
        print("\n✗ 未检测到有效 key，请确认 .env 已填写且已重启进程。")
        return

    print("\n" + "=" * 60)
    print("步骤1：实时联网检索价格（fetch_live_prices，返回版本列表）")
    print("=" * 60)
    keyword = "丰田卡罗拉 2024款 1.2T 指导价 优惠价"
    print(f"查询词：{keyword}")
    live = await fetch_live_prices(keyword)
    if live:
        print(f"✓ 实时检索成功，共 {len(live)} 个版本：")
        for c in live:
            print(f"  - {c.config} | {c.energy_type} | 指导 {c.guide_price} 万 / 优惠 {c.ref_discount_price} 万")
    else:
        print("✗ 实时检索未返回可用价格（模型未查到 / 抽取校验失败）。")

    print("\n" + "=" * 60)
    print("步骤2：带三级降级的取价（get_car_price，含 options 多版本）")
    print("=" * 60)
    result2 = await get_car_price(keyword)
    print(
        json.dumps(
            {
                "source": result2.source,
                "is_reference": result2.is_reference,
                "note": result2.note,
                "versions": len(result2.options),
                "data": result2.data.model_dump() if result2.data else None,
                "options": [o.model_dump() for o in result2.options],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    car = result2.data

    print("\n" + "=" * 60)
    print("步骤3：端到端决策计算（run_plan）")
    print("=" * 60)
    if not car:
        print("✗ 没有可取用的车型价格，跳过决策计算。请先完成模型/插件开通。")
        print("\n联调未完成：缺少实时价格。")
        return
    price = car.ref_discount_price or car.guide_price
    params = CalcParams(
        # 购车：裸车价（万元，来自车型价）
        price=price,
        mode="loan",
        down_payment_ratio=0.3,
        months=36,
        annual_rate=0.04,
        # 收入/支出（单位：万元/月）
        income=2.0,          # 2 万元/月 = 20000 元
        monthly_expense=0.7,  # 0.7 万元/月 = 7000 元
        savings=8.0,         # 8 万元储蓄
        # 用车能源：使用查询车型的真实能源类型与能耗
        energy_type=car.energy_type,
        fuel_consumption=car.fuel_consumption,
        power_consumption=car.power_consumption,
        fuel_price=7.8,
        electricity_price=0.6,
        monthly_km=1000,
    )
    result = run_plan(params)
    print(
        json.dumps(
            {
                "disposable_income": result.disposable_income,
                "monthly_payment": result.monthly_payment,
                "energy_cost_month": result.energy_cost_month,
                "fuel_cost_month": result.fuel_cost_month,
                "electricity_cost_month": result.electricity_cost_month,
                "landed_price": result.landed_price,
                "verdict": result.verdict,
                "verdict_text": result.verdict_text,
                "reason": result.reason,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\n✓ 联调完成。")


if __name__ == "__main__":
    asyncio.run(main())
