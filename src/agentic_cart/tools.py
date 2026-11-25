import math
from pydantic import Field
from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

class PortfolioRiskConfig(FunctionBaseConfig, name="calculate_portfolio_risk"):
    risk_free_rate: float = Field(default=0.065, description="Annualized risk-free rate (e.g. 0.065 for 6.5%)")



@register_function(config_type=PortfolioRiskConfig, framework_wrappers=[LLMFrameworkEnum.NONE])
async def calculate_portfolio_risk_tool(config: PortfolioRiskConfig, builder: Builder):
    async def _calc_risk(expected_return: float, volatility: float, portfolio_value: float) -> str:
        """Computes annualized Sharpe Ratio and 95% 1-day Parametric Value at Risk (VaR)."""
        if volatility <= 0:
            return "Error: Volatility must be greater than 0."
        sharpe = (expected_return - config.risk_free_rate) / volatility
        daily_vol = volatility / math.sqrt(252)
        var_95 = portfolio_value * 1.645 * daily_vol
        return (
            f"Sharpe Ratio: {sharpe:.2f} | "
            f"95% 1-Day Parametric VaR: {var_95:,.2f} (based on {config.risk_free_rate*100:.2f}% risk-free rate)"
        )

    yield FunctionInfo.from_fn(
        _calc_risk,
        description="Calculate Sharpe Ratio and 95% 1-day Value at Risk (VaR) for a portfolio."
    )



class TransactionAuditConfig(FunctionBaseConfig, name="audit_transaction_aml"):
    high_value_threshold: float = Field(default=1000000.0, description="Flag threshold in base currency")


@register_function(config_type=TransactionAuditConfig, framework_wrappers=[LLMFrameworkEnum.NONE])
async def audit_transaction_aml_tool(config: TransactionAuditConfig, builder: Builder):
    async def _audit_tx(amount: float, jurisdiction: str, kyc_verified: bool) -> str:
        """Evaluates a financial transaction against AML/KYC rules and returns a risk flag."""
        flags = []
        if not kyc_verified:
            flags.append("CRITICAL: Unverified KYC status")
        if amount >= config.high_value_threshold:
            flags.append(f"HIGH_VALUE: Exceeds reporting threshold ({config.high_value_threshold:,.2f})")
        if jurisdiction.upper() in {"HIGH_RISK_JURISDICTION_A", "SANCTIONED"}:
            flags.append(f"JURISDICTION_ALERT: Restricted region ({jurisdiction})")

        status = "REVIEW_REQUIRED" if flags else "CLEARED"
        detail = "; ".join(flags) if flags else "All automated AML/KYC checks passed."
        return f"Audit Status: {status} | Details: {detail}"

    yield FunctionInfo.from_fn(
        _audit_tx,
        description="Audit a transaction for AML/KYC compliance, threshold limits, and jurisdiction risks."
    )    