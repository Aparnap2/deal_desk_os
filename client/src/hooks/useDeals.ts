import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'

import { apiClient } from '@lib/api'
import type { Deal, DealCollection } from '@shared/contracts/deal'

const DealFiltersSchema = z.object({
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(100).default(20),
  search: z.string().min(2).optional(),
  stage: z.string().optional(),
  ownerId: z.string().optional()
})

export type DealFilters = z.infer<typeof DealFiltersSchema>

const buildQueryString = (filters: DealFilters) => {
  const params = new URLSearchParams()
  
  params.set('page', String(filters.page ?? 1))
  params.set('page_size', String(filters.pageSize ?? 20))
  if (filters.search) params.set('search', filters.search)
  if (filters.stage) params.set('stage', filters.stage)
  if (filters.ownerId) params.set('owner_id', filters.ownerId)
  return params.toString()
}

export const useDeals = (filters: DealFilters) => {
  const parsed = DealFiltersSchema.parse(filters)
  return useQuery({
    queryKey: ['deals', parsed],
    queryFn: async (): Promise<DealCollection> => {
      const response = await apiClient.get(`/deals?${buildQueryString(parsed)}`)
      return response.data
    }
  })
}

export const useDeal = (dealId: string | undefined) => {
  return useQuery({
    queryKey: ['deal', dealId],
    queryFn: async (): Promise<Deal> => {
      const response = await apiClient.get(`/deals/${dealId}`)
      return response.data
    },
    enabled: Boolean(dealId)
  })
}

const DealInputSchema = z.object({
  name: z.string().min(3),
  description: z.string().nullable(),
  amount: z.string().refine((value) => Number(value) > 0, 'Amount must be positive'),
  currency: z.string().length(3).default('USD'),
  stage: z.string().optional(),
  risk: z.string().optional(),
  probability: z.number().min(0).max(100).optional(),
  expected_close: z.string().nullable().optional(),
  industry: z.string().nullable().optional(),
  owner_id: z.string().nullable().optional(),
  discount_percent: z
    .string()
    .default('0')
    .refine((value) => {
      const parsed = Number(value)
      return !Number.isNaN(parsed) && parsed >= 0 && parsed <= 100
    }, 'Discount must be between 0 and 100%'),
  payment_terms_days: z.number().int().min(0).max(365).default(30),
  orchestration_mode: z.enum(['manual', 'orchestrated']).default('orchestrated')
})

export type DealInput = z.infer<typeof DealInputSchema>

export const useCreateDeal = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: DealInput): Promise<Deal> => {
      const payload = DealInputSchema.parse(input)
      const response = await apiClient.post('/deals', {
        ...payload,
        amount: Number(payload.amount),
        discount_percent: Number(payload.discount_percent)
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deals'] })
    }
  })
}

export const useUpdateDeal = (dealId: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: Partial<DealInput>): Promise<Deal> => {
      const response = await apiClient.patch(`/deals/${dealId}`, input)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deal', dealId] })
      queryClient.invalidateQueries({ queryKey: ['deals'] })
    }
  })
}
