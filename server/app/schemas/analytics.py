from app.schemas.common import ORMModel


class TotalCostOfOwnership(ORMModel):
    manual: float
    orchestrated: float
    delta: float


class DashboardMetrics(ORMModel):
    median_time_to_cash_hours: float
    guardrail_compliance_rate: float
    failure_auto_recovery_rate: float
    cost_per_100_deals: float
    manual_vs_orchestrated_tco: TotalCostOfOwnership
