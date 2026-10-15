"""计算引擎单元测试：对齐技术方案第 8 节示例。"""
from app.engine.calc import calc_landed_price, calc_loan, calc_energy_cost
from app.engine.decision import evaluate
from app.engine import run_plan
from app.types import CalcParams


def test_landed_price():
    # 裸车价 17.5 万 -> 购置税≈1.55, 保险≈0.875, 杂费0.15, 落地≈20.08
    r = calc_landed_price(17.5)
    assert abs(r["purchase_tax"] - 1.5487) < 1e-3  # 17.5 / 11.3
    assert abs(r["insurance"] - 0.875) < 1e-3
    assert abs(r["landed_price"] - 20.0736) < 1e-3
    assert r["purchase_tax_halved"] is False


def test_landed_price_ev_tax_halved():
    # 电车购置税减半：17.5 / 11.3 / 2 ≈ 0.77
    r = calc_landed_price(17.5, energy_type="ev")
    assert abs(r["purchase_tax"] - 0.77435) < 1e-3
    assert r["purchase_tax_halved"] is True
    # 落地价相应降低（比油车少约 0.77 万购置税差）
    assert abs(r["landed_price"] - (20.0736 - 0.77435)) < 1e-2


def test_loan_monthly_payment():
    # 17.5 万, 首付30%, 36期, 年化4.5% -> 月供≈0.364 万
    r = calc_loan(17.5, 0.3, 36, 0.045)
    assert abs(r["monthly_payment"] - 0.3643) < 1e-2
    assert r["loan_amount"] == 12.25


def test_decision_green():
    d = evaluate("loan", monthly_payment=0.236, disposable_income=1.0, savings=10,
                 landed_price=20, monthly_expense=0.3, safe_ratio=0.3)
    assert d["verdict"] == "buy"
    assert d["verdict_text"] == "买买买"


def test_decision_yellow():
    # 月供占 D(1.0) 的 42% -> 黄灯
    d = evaluate("loan", monthly_payment=0.42, disposable_income=1.0, savings=10,
                 landed_price=20, monthly_expense=0.3, safe_ratio=0.3)
    assert d["verdict"] == "consider"


def test_decision_red_over_half():
    d = evaluate("loan", monthly_payment=0.6, disposable_income=1.0, savings=10,
                 landed_price=20, monthly_expense=0.3, safe_ratio=0.3)
    assert d["verdict"] == "avoid"


def test_decision_full_no_buffer():
    # 全款后储蓄见底 -> 红灯
    d = evaluate("full", monthly_payment=0, disposable_income=1.0, savings=21,
                 landed_price=20, monthly_expense=2, safe_ratio=0.3)
    assert d["verdict"] == "avoid"


def test_run_plan_full():
    p = CalcParams(price=17.5, mode="full", income=2.0, monthly_expense=0.5, savings=30)
    res = run_plan(p)
    assert res.mode == "full"
    assert abs(res.landed_price - 20.08) < 0.1
    assert res.monthly_payment == 0.0
    assert res.verdict == "buy"  # 全款后仍有充足缓冲


def test_run_plan_loan():
    p = CalcParams(price=17.5, mode="loan", down_payment_ratio=0.3, months=36,
                   annual_rate=0.045, income=1.5, monthly_expense=0.3, savings=10)
    res = run_plan(p)
    assert res.mode == "loan"
    assert abs(res.monthly_payment - 0.36) < 0.05
    assert res.disposable_income == 1.2
    assert res.safe_monthly_payment == 0.36  # 1.2 * 0.3


def test_energy_cost_gas():
    # 油车 8L/100km, 油价7.5, 月1000km -> 600元=0.06万
    r = calc_energy_cost("gas", fuel_consumption=8, fuel_price=7.5, monthly_km=1000)
    assert abs(r["fuel_cost_month"] - 0.06) < 1e-4
    assert r["electricity_cost_month"] == 0.0
    assert abs(r["energy_cost_month"] - 0.06) < 1e-4


def test_energy_cost_ev():
    # 电车 15kWh/100km, 电价0.6, 月1000km -> 90元=0.009万
    r = calc_energy_cost("ev", power_consumption=15, electricity_price=0.6, monthly_km=1000)
    assert abs(r["electricity_cost_month"] - 0.009) < 1e-4
    assert r["fuel_cost_month"] == 0.0


def test_run_plan_energy_reduces_disposable():
    # 油车 8L/100km -> 能源费0.06万计入月度支出，可支配收入由1.2降到1.14
    p = CalcParams(price=17.5, mode="loan", down_payment_ratio=0.3, months=36,
                   annual_rate=0.045, income=1.5, monthly_expense=0.3, savings=10,
                   energy_type="gas", fuel_consumption=8, fuel_price=7.5, monthly_km=1000)
    res = run_plan(p)
    assert abs(res.fuel_cost_month - 0.06) < 1e-3
    assert abs(res.disposable_income - 1.14) < 1e-3  # 1.5 - 0.3 - 0.06
    assert abs(res.safe_monthly_payment - 0.34) < 1e-3  # round(1.14 * 0.3) = 0.34


def test_run_plan_ev_purchase_tax_halved():
    # 电车：购置税减半且标记开启
    p = CalcParams(price=17.5, mode="full", income=2.0, monthly_expense=0.5, savings=30,
                   energy_type="ev", power_consumption=15, electricity_price=0.6, monthly_km=1000)
    res = run_plan(p)
    assert res.purchase_tax_halved is True
    assert abs(res.purchase_tax - 0.77) < 0.05
    # 落地价应等于 油车落地价 - 减半的购置税差（2 位四舍五入，容差放宽）
    gas = run_plan(CalcParams(price=17.5, mode="full", income=2.0, monthly_expense=0.5, savings=30, energy_type="gas"))
    assert abs(res.landed_price - (gas.landed_price - (gas.purchase_tax - res.purchase_tax))) < 0.02

