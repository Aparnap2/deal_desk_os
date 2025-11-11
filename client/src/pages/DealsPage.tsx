import { useState } from 'react'
import { toast } from 'sonner'

import { DealForm } from '@components/deals/DealForm'
import { DealTable } from '@components/deals/DealTable'
import { useCreateDeal, useDeals } from '@hooks/useDeals'

export const DealsPage = () => {
  const [showForm, setShowForm] = useState(false)
  const [page, setPage] = useState(1)
  const { data, isLoading } = useDeals({ page, pageSize: 20 })
  const createDeal = useCreateDeal()

  const handleSubmit = async (input: Parameters<typeof createDeal.mutateAsync>[0]) => {
    await createDeal.mutateAsync(input)
    toast.success('Deal created successfully')
    setShowForm(false)
  }

  return (
    <div className="card">
      <div className="card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="card__title">Deals</h2>
        <button className="button" onClick={() => setShowForm((value) => !value)} type="button">
          {showForm ? 'Hide form' : 'New deal'}
        </button>
      </div>
      {showForm ? (
        <DealForm onCancel={() => setShowForm(false)} onSubmit={handleSubmit} isSubmitting={createDeal.isPending} />
      ) : null}
      {isLoading ? <div>Loading deals...</div> : <DealTable deals={data?.items ?? []} />}
      {data && data.total > data.page_size ? (
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '16px' }}>
          <button className="button" type="button" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
            Previous
          </button>
          <button
            className="button"
            type="button"
            disabled={page * data.page_size >= data.total}
            onClick={() => setPage((value) => value + 1)}
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  )
}
