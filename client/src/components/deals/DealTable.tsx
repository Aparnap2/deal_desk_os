import { Link } from 'react-router-dom'

import type { DealSummary } from '@shared/contracts/deal'

type DealTableProps = {
  deals: DealSummary[]
}

const stageBadgeClass = (stage: string) => {
  if (stage === 'closed_won') return 'badge badge--success'
  if (stage === 'closed_lost') return 'badge badge--danger'
  return 'badge badge--warning'
}

export const DealTable = ({ deals }: DealTableProps) => {
  if (deals.length === 0) {
    return <div className="empty-state">No deals yet. Create your first deal to start tracking momentum.</div>
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Owner</th>
          <th>Stage</th>
          <th>Probability</th>
          <th>Amount</th>
          <th>Expected Close</th>
          <th>Guardrail</th>
          <th>Discount</th>
          <th>Terms</th>
        </tr>
      </thead>
      <tbody>
        {deals.map((deal) => (
          <tr key={deal.id}>
            <td>
              <Link to={`/deals/${deal.id}`}>{deal.name}</Link>
            </td>
            <td>{deal.owner?.full_name ?? 'Unassigned'}</td>
            <td>
              <span className={stageBadgeClass(deal.stage)}>{deal.stage.replace('_', ' ')}</span>
            </td>
            <td>{deal.probability}%</td>
            <td>${Number(deal.amount).toLocaleString()}</td>
            <td>{deal.expected_close ? new Date(deal.expected_close).toLocaleDateString() : '—'}</td>
            <td>
              <span className={deal.guardrail_status === 'pass' ? 'badge badge--success' : 'badge badge--danger'}>
                {deal.guardrail_status === 'pass' ? 'Within guardrail' : 'Violation'}
              </span>
            </td>
            <td>{Number(deal.discount_percent).toFixed(1)}%</td>
            <td>{deal.payment_terms_days} days</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
