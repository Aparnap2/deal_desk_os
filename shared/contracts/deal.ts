import type { CurrentUser } from './user'

export type DealStage =
  | 'prospecting'
  | 'qualification'
  | 'solutioning'
  | 'pricing'
  | 'legal_review'
  | 'finance_review'
  | 'executive_approval'
  | 'closed_won'
  | 'closed_lost'

export type DealRisk = 'low' | 'medium' | 'high'

export type GuardrailStatus = 'pass' | 'violated'

export type OrchestrationMode = 'manual' | 'orchestrated'

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'escalated'

export type DealDocumentStatus = 'draft' | 'in_review' | 'approved' | 'outdated'

export type DealApproval = {
  id: string
  approver_id: string | null
  status: ApprovalStatus
  notes: string | null
  due_at: string | null
  completed_at: string | null
  sequence_order: number
  deal_id: string
  created_at: string
  updated_at: string
}

export type DealDocument = {
  id: string
  name: string
  uri: string
  status: DealDocumentStatus
  version: string | null
  deal_id: string
  created_at: string
  updated_at: string
}

export type DealSummary = {
  id: string
  name: string
  amount: string
  probability: number
  stage: DealStage
  risk: DealRisk
  owner: CurrentUser | null
  expected_close: string | null
  updated_at: string
  discount_percent: string
  payment_terms_days: number
  guardrail_status: GuardrailStatus
  orchestration_mode: OrchestrationMode
  quote_generated_at: string | null
  payment_collected_at: string | null
}

export type Deal = DealSummary & {
  description: string | null
  currency: string
  industry: string | null
  approvals: DealApproval[]
  documents: DealDocument[]
  created_at: string
  agreement_signed_at: string | null
  guardrail_reason: string | null
  operational_cost: string
  manual_cost_baseline: string
  esign_envelope_id: string | null
  guardrail_locked: boolean
}

export type DealCollection = {
  items: DealSummary[]
  total: number
  page: number
  page_size: number
}
