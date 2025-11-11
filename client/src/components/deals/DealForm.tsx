import { useState } from 'react'

import type { DealInput } from '@hooks/useDeals'

type DealFormProps = {
  onSubmit: (input: DealInput) => Promise<void>
  onCancel: () => void
  isSubmitting: boolean
}

const initialFormState: DealInput = {
  name: '',
  description: null,
  amount: '0',
  currency: 'USD',
  stage: 'prospecting',
  risk: 'medium',
  probability: 25,
  expected_close: null,
  industry: null,
  owner_id: null,
  discount_percent: '0',
  payment_terms_days: 30,
  orchestration_mode: 'orchestrated'
}

export const DealForm = ({ onSubmit, onCancel, isSubmitting }: DealFormProps) => {
  const [form, setForm] = useState<DealInput>(initialFormState)

  const handleChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = event.target
    if (name === 'probability') {
      setForm((prev) => ({ ...prev, probability: Number(value) }))
      return
    }
    if (name === 'payment_terms_days') {
      setForm((prev) => ({ ...prev, payment_terms_days: Number(value) }))
      return
    }
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const submitForm = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await onSubmit(form)
    setForm(initialFormState)
  }

  return (
    <form className="form" onSubmit={submitForm}>
      <div className="form-group">
        <label htmlFor="name">Deal name</label>
        <input id="name" name="name" required value={form.name} onChange={handleChange} />
      </div>
      <div className="form-group">
        <label htmlFor="description">Description</label>
        <textarea id="description" name="description" value={form.description ?? ''} onChange={handleChange} rows={3} />
      </div>
      <div className="form-group">
        <label htmlFor="amount">Amount (USD)</label>
        <input id="amount" name="amount" type="number" step="0.01" min="0" value={form.amount} onChange={handleChange} />
      </div>
      <div className="form-group">
        <label htmlFor="stage">Stage</label>
        <select id="stage" name="stage" value={form.stage} onChange={handleChange}>
          <option value="prospecting">Prospecting</option>
          <option value="qualification">Qualification</option>
          <option value="solutioning">Solutioning</option>
          <option value="pricing">Pricing</option>
          <option value="legal_review">Legal Review</option>
          <option value="finance_review">Finance Review</option>
          <option value="executive_approval">Executive Approval</option>
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="probability">Probability (%)</label>
        <input id="probability" name="probability" type="number" min="0" max="100" value={form.probability ?? 0} onChange={handleChange} />
      </div>
      <div className="form-group">
        <label htmlFor="discount_percent">Discount (%)</label>
        <input
          id="discount_percent"
          name="discount_percent"
          type="number"
          step="0.1"
          min="0"
          max="100"
          value={form.discount_percent}
          onChange={handleChange}
        />
      </div>
      <div className="form-group">
        <label htmlFor="payment_terms_days">Payment terms (days)</label>
        <input
          id="payment_terms_days"
          name="payment_terms_days"
          type="number"
          min="0"
          max="365"
          value={form.payment_terms_days}
          onChange={handleChange}
        />
      </div>
      <div className="form-group">
        <label htmlFor="orchestration_mode">Orchestration mode</label>
        <select id="orchestration_mode" name="orchestration_mode" value={form.orchestration_mode} onChange={handleChange}>
          <option value="orchestrated">Orchestrated</option>
          <option value="manual">Manual</option>
        </select>
      </div>
      <div className="form-actions">
        <button className="button" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Submitting…' : 'Create deal'}
        </button>
        <button className="button" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
