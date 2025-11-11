import { useDashboardMetrics } from '@hooks/useDashboardMetrics'

const formatPercent = (value: number) => `${value.toFixed(1)}%`
const formatCurrency = (value: number) =>
  `$${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
const formatHours = (value: number) => `${value.toFixed(1)}h`

export const DashboardPage = () => {
  const { data, isLoading } = useDashboardMetrics()

  if (isLoading || !data) {
    return <div>Loading RevOps telemetry...</div>
  }

  return (
    <div className="card-grid">
      <div className="card">
        <h2 className="card__title">Median Time to Cash</h2>
        <div className="card__metric">{formatHours(data.median_time_to_cash_hours)}</div>
      </div>
      <div className="card">
        <h2 className="card__title">Quotes Within Guardrails</h2>
        <div className="card__metric">{formatPercent(data.guardrail_compliance_rate)}</div>
      </div>
      <div className="card">
        <h2 className="card__title">Failures Auto-Recovered</h2>
        <div className="card__metric">{formatPercent(data.failure_auto_recovery_rate)}</div>
      </div>
      <div className="card">
        <h2 className="card__title">Cost per 100 Deals</h2>
        <div className="card__metric">{formatCurrency(data.cost_per_100_deals)}</div>
      </div>
      <div className="card">
        <h2 className="card__title">Manual vs Orchestrated TCO</h2>
        <div className="card__metric">
          {formatCurrency(data.manual_vs_orchestrated_tco.delta)} saved
        </div>
        <div className="card__submetric">
          <span>Manual: {formatCurrency(data.manual_vs_orchestrated_tco.manual)}</span>
          <span>Orchestrated: {formatCurrency(data.manual_vs_orchestrated_tco.orchestrated)}</span>
        </div>
      </div>
    </div>
  )
}
