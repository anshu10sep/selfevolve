"""
Fundamental Analyst — Real Financial Analysis Tools

Production-grade financial analysis tools that compute real metrics.
These replace the stub implementations with deterministic calculations.

All functions are deterministic (no LLM) — they compute math from data.
"""

from typing import Dict, Any, List, Optional
import logging

from agents.skills.validator import skill

logger = logging.getLogger(__name__)


@skill("fundamental_analyst")
def analyze_financial_ratios(
    revenue: float,
    net_income: float,
    total_assets: float,
    total_liabilities: float,
    current_assets: float,
    current_liabilities: float,
    total_equity: float,
    shares_outstanding: float,
    current_price: float,
    operating_cash_flow: float = 0.0,
    dividends_paid: float = 0.0,
) -> Dict[str, Any]:
    """
    Compute key financial ratios from raw financial statement data.
    These ratios help evaluate profitability, liquidity, solvency, and valuation.

    Args:
        revenue: Total revenue (TTM).
        net_income: Net income (TTM).
        total_assets: Total assets.
        total_liabilities: Total liabilities.
        current_assets: Current (short-term) assets.
        current_liabilities: Current (short-term) liabilities.
        total_equity: Total shareholders' equity.
        shares_outstanding: Number of outstanding shares.
        current_price: Current stock price per share.
        operating_cash_flow: Operating cash flow (TTM).
        dividends_paid: Total dividends paid (TTM, positive number).

    Returns:
        Dict with profitability, liquidity, solvency, and valuation ratios plus overall assessment.
    """
    if shares_outstanding <= 0 or current_price <= 0:
        return {"error": "Invalid shares_outstanding or current_price", "assessment": "error"}

    market_cap = current_price * shares_outstanding
    eps = net_income / shares_outstanding if shares_outstanding > 0 else 0
    bvps = total_equity / shares_outstanding if shares_outstanding > 0 else 0

    # Profitability ratios
    net_margin = round(net_income / revenue, 4) if revenue > 0 else 0
    roa = round(net_income / total_assets, 4) if total_assets > 0 else 0
    roe = round(net_income / total_equity, 4) if total_equity > 0 else 0

    # Liquidity ratios
    current_ratio = round(current_assets / current_liabilities, 2) if current_liabilities > 0 else 999
    working_capital = current_assets - current_liabilities

    # Solvency ratios
    debt_to_equity = round(total_liabilities / total_equity, 2) if total_equity > 0 else 999
    debt_to_assets = round(total_liabilities / total_assets, 2) if total_assets > 0 else 1

    # Valuation ratios
    pe_ratio = round(current_price / eps, 2) if eps > 0 else None
    pb_ratio = round(current_price / bvps, 2) if bvps > 0 else None
    ps_ratio = round(market_cap / revenue, 2) if revenue > 0 else None

    # Free cash flow yield
    fcf_yield = round(operating_cash_flow / market_cap, 4) if market_cap > 0 else 0
    dividend_yield = round(dividends_paid / market_cap, 4) if market_cap > 0 else 0

    # Assessment scoring
    score = 0
    notes = []

    # Profitability scoring
    if net_margin > 0.15:
        score += 2; notes.append("Strong margins (>15%)")
    elif net_margin > 0.05:
        score += 1; notes.append("Decent margins (5-15%)")
    elif net_margin < 0:
        score -= 2; notes.append("Negative margins")

    if roe > 0.15:
        score += 2; notes.append("Strong ROE (>15%)")
    elif roe > 0.08:
        score += 1; notes.append("Decent ROE (8-15%)")

    # Liquidity scoring
    if current_ratio >= 2.0:
        score += 1; notes.append("Strong liquidity")
    elif current_ratio < 1.0:
        score -= 2; notes.append("Weak liquidity (<1.0)")

    # Solvency scoring
    if debt_to_equity < 0.5:
        score += 1; notes.append("Low leverage")
    elif debt_to_equity > 2.0:
        score -= 2; notes.append("High leverage (>2x)")

    # Valuation scoring
    if pe_ratio is not None:
        if pe_ratio < 15:
            score += 1; notes.append(f"Value P/E ({pe_ratio})")
        elif pe_ratio > 40:
            score -= 1; notes.append(f"Expensive P/E ({pe_ratio})")

    if score >= 4:
        assessment = "strong_buy"
    elif score >= 2:
        assessment = "buy"
    elif score >= 0:
        assessment = "hold"
    elif score >= -2:
        assessment = "weak"
    else:
        assessment = "sell"

    return {
        "profitability": {
            "net_margin": net_margin,
            "roa": roa,
            "roe": roe,
            "eps": round(eps, 4),
        },
        "liquidity": {
            "current_ratio": current_ratio,
            "working_capital": round(working_capital, 2),
        },
        "solvency": {
            "debt_to_equity": debt_to_equity,
            "debt_to_assets": debt_to_assets,
        },
        "valuation": {
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "ps_ratio": ps_ratio,
            "market_cap": round(market_cap, 2),
            "fcf_yield": fcf_yield,
            "dividend_yield": dividend_yield,
        },
        "composite_score": score,
        "assessment": assessment,
        "notes": notes,
    }


@skill("fundamental_analyst")
def compute_dcf_valuation(
    free_cash_flows: List[float],
    growth_rate: float,
    terminal_growth_rate: float,
    discount_rate: float,
    shares_outstanding: float,
    net_debt: float = 0.0,
) -> Dict[str, Any]:
    """
    Compute a Discounted Cash Flow (DCF) valuation.
    Projects future free cash flows and discounts them to present value.

    Args:
        free_cash_flows: List of historical FCFs (most recent last). Minimum 1.
        growth_rate: Expected annual FCF growth rate (e.g., 0.10 for 10%).
        terminal_growth_rate: Long-term perpetual growth rate (e.g., 0.025 for 2.5%).
        discount_rate: Weighted Average Cost of Capital (WACC) (e.g., 0.10 for 10%).
        shares_outstanding: Number of outstanding shares.
        net_debt: Total debt minus cash (positive = net debt, negative = net cash).

    Returns:
        Dict with intrinsic_value_per_share, projected_fcfs, terminal_value, enterprise_value.
    """
    if not free_cash_flows or shares_outstanding <= 0:
        return {"error": "Invalid inputs", "intrinsic_value_per_share": None}

    if discount_rate <= terminal_growth_rate:
        return {
            "error": "Discount rate must exceed terminal growth rate",
            "intrinsic_value_per_share": None,
        }

    base_fcf = free_cash_flows[-1]
    projection_years = 5

    # Project future FCFs
    projected = []
    for year in range(1, projection_years + 1):
        projected_fcf = base_fcf * (1 + growth_rate) ** year
        pv = projected_fcf / (1 + discount_rate) ** year
        projected.append({
            "year": year,
            "fcf": round(projected_fcf, 2),
            "present_value": round(pv, 2),
        })

    # Terminal value (Gordon Growth Model)
    terminal_fcf = base_fcf * (1 + growth_rate) ** projection_years * (1 + terminal_growth_rate)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth_rate)
    tv_present_value = terminal_value / (1 + discount_rate) ** projection_years

    # Enterprise value
    total_pv_fcfs = sum(p["present_value"] for p in projected)
    enterprise_value = total_pv_fcfs + tv_present_value

    # Equity value
    equity_value = enterprise_value - net_debt
    intrinsic_value = equity_value / shares_outstanding

    return {
        "intrinsic_value_per_share": round(intrinsic_value, 2),
        "enterprise_value": round(enterprise_value, 2),
        "equity_value": round(equity_value, 2),
        "terminal_value": round(terminal_value, 2),
        "terminal_pv": round(tv_present_value, 2),
        "projected_fcfs": projected,
        "assumptions": {
            "growth_rate": growth_rate,
            "terminal_growth_rate": terminal_growth_rate,
            "discount_rate": discount_rate,
            "projection_years": projection_years,
            "base_fcf": base_fcf,
        },
    }


@skill("fundamental_analyst")
def evaluate_earnings_quality(
    net_income: float,
    operating_cash_flow: float,
    revenue: float,
    accounts_receivable: float,
    prev_accounts_receivable: float,
    inventory: float,
    prev_inventory: float,
    depreciation: float,
    total_assets: float,
) -> Dict[str, Any]:
    """
    Evaluate the quality of a company's reported earnings using accrual analysis.
    High-quality earnings are backed by real cash flows, not accounting tricks.

    Args:
        net_income: Net income (TTM).
        operating_cash_flow: Operating cash flow (TTM).
        revenue: Total revenue (TTM).
        accounts_receivable: Current accounts receivable.
        prev_accounts_receivable: Previous period accounts receivable.
        inventory: Current inventory.
        prev_inventory: Previous period inventory.
        depreciation: Depreciation & amortization.
        total_assets: Total assets.

    Returns:
        Dict with quality scores, accrual ratio, cash conversion, and flags.
    """
    flags = []
    quality_score = 100

    # 1. Cash conversion: OCF should be close to or exceed net income
    if net_income != 0:
        cash_conversion = round(operating_cash_flow / net_income, 2)
    else:
        cash_conversion = 0.0

    if cash_conversion < 0.8:
        quality_score -= 25
        flags.append(f"Low cash conversion ({cash_conversion}x) — earnings not well-backed by cash")
    elif cash_conversion > 1.2:
        flags.append(f"Strong cash conversion ({cash_conversion}x) — cash exceeds reported earnings")

    # 2. Accrual ratio (Sloan): high accruals = lower quality
    accruals = net_income - operating_cash_flow + depreciation
    accrual_ratio = round(accruals / total_assets, 4) if total_assets > 0 else 0

    if abs(accrual_ratio) > 0.10:
        quality_score -= 20
        flags.append(f"High accrual ratio ({accrual_ratio}) — potential earnings manipulation")

    # 3. Receivables growth vs revenue growth
    ar_growth = (accounts_receivable - prev_accounts_receivable) / prev_accounts_receivable if prev_accounts_receivable > 0 else 0
    if ar_growth > 0.15:
        quality_score -= 15
        flags.append(f"Receivables growing faster than normal ({ar_growth:.1%}) — possible channel stuffing")

    # 4. Inventory buildup
    inv_growth = (inventory - prev_inventory) / prev_inventory if prev_inventory > 0 else 0
    if inv_growth > 0.20:
        quality_score -= 15
        flags.append(f"Inventory building up ({inv_growth:.1%}) — possible demand weakness")

    quality_score = max(0, quality_score)

    if quality_score >= 80:
        assessment = "high_quality"
    elif quality_score >= 60:
        assessment = "acceptable"
    elif quality_score >= 40:
        assessment = "questionable"
    else:
        assessment = "low_quality"

    return {
        "quality_score": quality_score,
        "assessment": assessment,
        "cash_conversion_ratio": cash_conversion,
        "accrual_ratio": accrual_ratio,
        "receivables_growth": round(ar_growth, 4),
        "inventory_growth": round(inv_growth, 4),
        "flags": flags,
    }
