import { useQuery } from '@tanstack/react-query'

import { apiClient } from '@lib/api'
import type { DashboardMetrics } from '@shared/contracts/analytics'

export const useDashboardMetrics = () =>
  useQuery({
    queryKey: ['dashboard-metrics'],
    queryFn: async (): Promise<DashboardMetrics> => {
      const response = await apiClient.get('/analytics/dashboard')
      return response.data
    },
    staleTime: 60_000
  })
