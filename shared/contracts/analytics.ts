export type TotalCostOfOwnership = {
  manual: number
  orchestrated: number
  delta: number
}

export type DashboardMetrics = {
  median_time_to_cash_hours: number
  guardrail_compliance_rate: number
  failure_auto_recovery_rate: number
  cost_per_100_deals: number
  manual_vs_orchestrated_tco: TotalCostOfOwnership
}
