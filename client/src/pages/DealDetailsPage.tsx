import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { useDeal, useUpdateDeal } from '@hooks/useDeals'

const stageOptions = [
  'prospecting',
  'qualification',
  'solutioning',
  'pricing',
  'legal_review',
  'finance_review',
  'executive_approval',
  'closed_won',
  'closed_lost'
]

export const DealDetailsPage = () => {
  const { dealId } = useParams()
  const { data, isLoading } = useDeal(dealId)
  const updateDeal = useUpdateDeal(dealId ?? '')

  const approvalTimeline = useMemo(() => {
    if (!data) return []
    return [...data.approvals].sort((a, b) => a.sequence_order - b.sequence_order)
  }, [data])

  const changeStage = async (event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextStage = event.target.value
    if (!dealId) return
    await updateDeal.mutateAsync({ stage: nextStage })
    toast.success('Deal stage updated')
  }

  if (isLoading || !data) {
    return <div>Loading deal...</div>
  }

  const timeToCashHours = data.quote_generated_at && data.payment_collected_at
    ? Math.max(
        0,
        (new Date(data.payment_collected_at).getTime() - new Date(data.quote_generated_at).getTime()) / 3_600_000
      )
    : null

  const formatCurrency = (value: string) => `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 0 })}`

  const guardrailBadgeClass = data.guardrail_status === 'pass' ? 'badge badge--success' : 'badge badge--danger'

  return (
    <div className="card" style={{ gap: '24px' }}>
      <div>
        <h2 className="card__title">{data.name}</h2>
        <p>{data.description ?? 'No description'}</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
          <div>
            <strong>Stage</strong>
            <select value={data.stage} onChange={changeStage} style={{ marginTop: '8px' }}>
              {stageOptions.map((stage) => (
                <option key={stage} value={stage}>
                  {stage.replace('_', ' ')}
                </option>
              ))}
            </select>
          </div>
          <div>
            <strong>Amount</strong>
            <div>${Number(data.amount).toLocaleString()}</div>
          </div>
          <div>
            <strong>Probability</strong>
            <div>{data.probability}%</div>
          </div>
          <div>
            <strong>Owner</strong>
            <div>{data.owner?.full_name ?? 'Unassigned'}</div>
          </div>
          <div>
            <strong>Guardrail status</strong>
            <div style={{ marginTop: '8px' }}>
              <span className={guardrailBadgeClass}>
                {data.guardrail_status === 'pass' ? 'Within guardrail' : 'Violation'}
              </span>
            </div>
            {data.guardrail_reason ? <p style={{ marginTop: '8px' }}>{data.guardrail_reason}</p> : null}
          </div>
          <div>
            <strong>Discount</strong>
            <div>{Number(data.discount_percent).toFixed(1)}%</div>
          </div>
          <div>
            <strong>Payment terms</strong>
            <div>{data.payment_terms_days} days</div>
          </div>
          <div>
            <strong>Orchestration</strong>
            <div style={{ textTransform: 'capitalize' }}>{data.orchestration_mode}</div>
          </div>
          <div>
            <strong>Operational cost</strong>
            <div>{formatCurrency(data.operational_cost)}</div>
          </div>
          <div>
            <strong>Manual baseline</strong>
            <div>{formatCurrency(data.manual_cost_baseline)}</div>
          </div>
          <div>
            <strong>Time to cash</strong>
            <div>{timeToCashHours !== null ? `${timeToCashHours.toFixed(1)}h` : 'Awaiting payment'}</div>
          </div>
        </div>
      </div>
      <section>
        <h3 className="card__title">Milestones</h3>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '12px' }}>
          <li>
            <strong>Quote generated</strong>
            <div>{data.quote_generated_at ? new Date(data.quote_generated_at).toLocaleString() : 'Pending'}</div>
          </li>
          <li>
            <strong>E-sign envelope</strong>
            <div>{data.esign_envelope_id ?? 'Not yet sent'}</div>
          </li>
          <li>
            <strong>Payment collected</strong>
            <div>{data.payment_collected_at ? new Date(data.payment_collected_at).toLocaleString() : 'Pending'}</div>
          </li>
        </ul>
      </section>
      <section>
        <h3 className="card__title">Approval workflow</h3>
        {approvalTimeline.length === 0 ? (
          <div className="empty-state">No approvals configured for this deal.</div>
        ) : (
          <ol style={{ listStyle: 'decimal', paddingLeft: '16px', display: 'grid', gap: '12px' }}>
            {approvalTimeline.map((approval) => (
              <li key={approval.id}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{approval.approver_id ?? 'Unassigned approver'}</span>
                  <span>{approval.status.toUpperCase()}</span>
                </div>
                {approval.notes ? <p style={{ marginTop: '4px' }}>{approval.notes}</p> : null}
              </li>
            ))}
          </ol>
        )}
      </section>
      <section>
        <h3 className="card__title">Documents</h3>
        {data.documents.length === 0 ? (
          <div className="empty-state">No documents uploaded.</div>
        ) : (
          <ul style={{ paddingLeft: '16px' }}>
            {data.documents.map((doc) => (
              <li key={doc.id}>
                <a href={doc.uri} target="_blank" rel="noreferrer">
                  {doc.name}
                </a>{' '}
                <span>({doc.status})</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
