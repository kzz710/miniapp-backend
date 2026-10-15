"""可负担性评估引擎（纯函数）。

规则来源：技术方案第 8.3 节三档评估。
定义：
- 可支配收入 D = 月收入 − 月固定支出
- 安全月供线 S = D × 安全比例（默认 0.3）
- 绿灯（买买买）：月供 ≤ S；全款时储蓄缓冲 ≥ 3 个月支出
- 黄灯（理性考虑）：月供占 D 的 30% ~ 50%
- 红灯（买个 der）：月供占 D > 50%，或全款后储蓄见底
"""
from typing import Literal

SAFE_RATIO = 0.3


def evaluate(
    mode: Literal["full", "loan"],
    monthly_payment: float,
    disposable_income: float,
    savings: float,
    landed_price: float,
    monthly_expense: float,
    safe_ratio: float = SAFE_RATIO,
) -> dict:
    safe = disposable_income * safe_ratio

    if mode == "full":
        buffer = savings - landed_price
        months_buffer = buffer / monthly_expense if monthly_expense > 0 else float("inf")
        if buffer >= monthly_expense * 3:
            return _verdict(
                "buy",
                "买买买",
                f"全款后仍有约 {months_buffer:.1f} 个月支出缓冲，买买买！",
                safe,
                disposable_income,
            )
        return _verdict(
            "avoid",
            "买个 der",
            f"全款后储蓄见底（仅剩约 {months_buffer:.1f} 个月缓冲），风险高，先攒钱吧（买个 der）。",
            safe,
            disposable_income,
        )

    # 分期
    ratio = monthly_payment / disposable_income if disposable_income > 0 else float("inf")
    pct = ratio * 100
    if monthly_payment <= safe:
        return _verdict(
            "buy",
            "买买买",
            f"月供占可支配收入 {pct:.0f}%，压力可控，买买买！",
            safe,
            disposable_income,
            ratio,
        )
    if ratio <= 0.5:
        return _verdict(
            "consider",
            "理性考虑",
            f"月供占可支配收入 {pct:.0f}%，会明显压缩生活质量，建议理性考虑或提高首付。",
            safe,
            disposable_income,
            ratio,
        )
    return _verdict(
        "avoid",
        "买个 der",
        f"月供已超可支配收入一半（{pct:.0f}%），强行上车风险很高，先攒钱吧（买个 der）。",
        safe,
        disposable_income,
        ratio,
    )


def _verdict(verdict: str, text: str, reason: str, safe: float, disp: float, ratio=None) -> dict:
    return {
        "verdict": verdict,
        "verdict_text": text,
        "reason": reason,
        "safe_monthly_payment": safe,
        "disposable_income": disp,
        "ratio": ratio,
    }
