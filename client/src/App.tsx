import { Navigate, Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from '@components/ProtectedRoute'
import { AppLayout } from '@components/layout/AppLayout'
import { DashboardPage } from '@pages/DashboardPage'
import { DealDetailsPage } from '@pages/DealDetailsPage'
import { DealsPage } from '@pages/DealsPage'
import { LoginPage } from '@pages/LoginPage'
import PolicyManagement from '@pages/PolicyManagement'
import PolicyEditorPage from '@pages/PolicyEditorPage'

const App = () => {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="/deals" element={<DealsPage />} />
          <Route path="/deals/:dealId" element={<DealDetailsPage />} />
          <Route path="/policies" element={<PolicyManagement />} />
          <Route path="/policies/new" element={<PolicyEditorPage />} />
          <Route path="/policies/:policyId/edit" element={<PolicyEditorPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
