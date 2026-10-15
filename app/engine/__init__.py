"""引擎聚合：组合 calc + decision，产出最终 CalcResult。"""
from app.engine.calc import calc_energy_cost, calc_full_plan, calc_loan_plan
from app.engine.decision import SAFE_RATIO, evaluate
from app.types import CalcParams, CalcResult


def _round2(x: float) -> float:
    return round(x, 2)


def run_plan(params: CalcParams) -> CalcResult:
    """入参 -> 完整测算结果（含结论）。能源费计入每月固定支出，影响可支配收入与结论。"""
    price = params.price
    if params.mode == "loan":
        plan = calc_loan_plan(
            price, params.down_payment_ratio, params.months, params.annual_rate, params.energy_type
        )
    else:
        plan = calc_full_plan(price, params.energy_type)

    energy = calc_energy_cost(
        params.energy_type,
        params.fuel_consumption,
        params.power_consumption,
        params.monthly_km,
        params.fuel_price,
        params.electricity_price,
    )
    energy_cost_month = energy["energy_cost_month"]

    # 能源费是真实月度流出，计入固定支出，再算可支配收入
    effective_expense = params.monthly_expense + energy_cost_month
    disposable_income = params.income - effective_expense
    safe_ratio = params.safe_ratio or SAFE_RATIO
    safe = disposable_income * safe_ratio

    dec = evaluate(
        params.mode,
        plan.get("monthly_payment", 0.0),
        disposable_income,
        params.savings,
        plan["landed_price"],
        effective_expense,
        safe_ratio,
    )

    return CalcResult(
        mode=params.mode,
        landed_price=_round2(plan["landed_price"]),
        purchase_tax=_round2(plan["purchase_tax"]),
        purchase_tax_halved=plan.get("purchase_tax_halved", False),
        insurance=_round2(plan["insurance"]),
        misc_fee=_round2(plan["misc_fee"]),
        down_payment=_round2(plan.get("down_payment", plan["landed_price"])),
        loan_amount=_round2(plan.get("loan_amount", 0.0)),
        monthly_payment=_round2(plan.get("monthly_payment", 0.0)),
        total_interest=_round2(plan.get("total_interest", 0.0)),
        disposable_income=_round2(disposable_income),
        safe_monthly_payment=_round2(safe),
        energy_type=params.energy_type,
        fuel_cost_month=energy["fuel_cost_month"],
        electricity_cost_month=energy["electricity_cost_month"],
        energy_cost_month=energy_cost_month,
        monthly_km=params.monthly_km,
        verdict=dec["verdict"],
        verdict_text=dec["verdict_text"],
        reason=dec["reason"],
    )
