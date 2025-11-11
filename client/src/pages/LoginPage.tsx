import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import type { Location } from 'react-router-dom'
import { toast } from 'sonner'

import { useAuth } from '@hooks/useAuth'

type LocationState = {
  from?: Location
}

export const LoginPage = () => {
  const location = useLocation()
  const { login, user, isLoading } = useAuth()
  const [form, setForm] = useState({ email: '', password: '' })

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    try {
      await login(form)
      toast.success('Welcome back')
    } catch (error) {
      console.error(error)
      toast.error('Invalid credentials')
    }
  }

  if (user) {
    const state = location.state as LocationState | undefined
    return <Navigate to={state?.from?.pathname ?? '/'} replace />
  }

  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: '100vh', background: '#0f172a' }}>
      <form
        onSubmit={handleSubmit}
        style={{
          background: '#ffffff',
          padding: '32px',
          borderRadius: '12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          width: '320px'
        }}
      >
        <h1 style={{ margin: 0 }}>Deal Desk OS</h1>
        <p style={{ color: '#6b7280', margin: 0 }}>Sign in to continue</p>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          Email
          <input
            name="email"
            type="email"
            required
            value={form.email}
            onChange={handleChange}
            style={{ padding: '10px 12px', borderRadius: '8px', border: '1px solid #d1d5db' }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          Password
          <input
            name="password"
            type="password"
            required
            value={form.password}
            onChange={handleChange}
            style={{ padding: '10px 12px', borderRadius: '8px', border: '1px solid #d1d5db' }}
          />
        </label>
        <button className="button" type="submit" disabled={isLoading}>
          {isLoading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
