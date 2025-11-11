import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'

import { apiClient, setAccessToken } from '@lib/api'
import { AuthToken, clearToken, persistToken, readToken } from '@lib/auth'
import type { CurrentUser } from '@shared/contracts/user'

const CredentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8)
})

export type Credentials = z.infer<typeof CredentialsSchema>

type AuthContextValue = {
  user: CurrentUser | null
  token: AuthToken | null
  isLoading: boolean
  login: (input: Credentials) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const fetchCurrentUser = async (): Promise<CurrentUser> => {
  const response = await apiClient.get('/users/me')
  return response.data
}

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const queryClient = useQueryClient()
  const [token, setTokenState] = useState<AuthToken | null>(() => readToken())

  useEffect(() => {
    setAccessToken(token?.token ?? null)
  }, [token])

  const { data: user, isFetching } = useQuery({
    queryKey: ['current-user'],
    queryFn: fetchCurrentUser,
    enabled: Boolean(token)
  })

  const loginMutation = useMutation({
    mutationFn: async (input: Credentials) => {
      const payload = CredentialsSchema.parse(input)
      const params = new URLSearchParams({
        username: payload.email,
        password: payload.password,
        grant_type: 'password'
      })
      const response = await apiClient.post('/auth/token', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      const expiresAt = Date.now() + response.data.expires_in * 1000
      const nextToken: AuthToken = { token: response.data.access_token, expiresAt }
      persistToken(nextToken)
      setTokenState(nextToken)
      setAccessToken(nextToken.token)
      await queryClient.invalidateQueries({ queryKey: ['current-user'] })
    }
  })

  const logout = () => {
    clearToken()
    setTokenState(null)
    setAccessToken(null)
    queryClient.clear()
  }

  const value = useMemo<AuthContextValue>(() => ({
    user: user ?? null,
    token,
    isLoading: isFetching || loginMutation.isPending,
    login: async (input) => loginMutation.mutateAsync(input),
    logout
  }), [user, token, isFetching, loginMutation, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
