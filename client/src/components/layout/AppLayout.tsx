import { Outlet } from 'react-router-dom'

import { useAuth } from '@hooks/useAuth'

import { Sidebar } from './Sidebar'
import { TopNav } from './TopNav'

import '../../styles/app.css'

export const AppLayout = () => {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <TopNav user={user} onLogout={logout} />
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
