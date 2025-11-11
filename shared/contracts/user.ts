export type UserRole = 'sales' | 'legal' | 'finance' | 'executive' | 'admin'

export type CurrentUser = {
  id: string
  email: string
  full_name: string
  roles: UserRole[]
  is_active: boolean
  created_at: string
  updated_at: string
}
