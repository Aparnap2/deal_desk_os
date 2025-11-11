import type { CurrentUser } from '@shared/contracts/user'

type TopNavProps = {
  user: CurrentUser | null
  onLogout: () => void
}

export const TopNav = ({ user, onLogout }: TopNavProps) => {
  return (
    <header className="top-nav">
      <h1 className="top-nav__title">Deal Desk OS</h1>
      {user ? (
        <div className="top-nav__actions">
          <div className="top-nav__user">
            <span className="top-nav__user-name">{user.full_name}</span>
            <span className="top-nav__user-role">{user.roles.join(', ')}</span>
          </div>
          <button className="button" onClick={onLogout} type="button">
            Sign out
          </button>
        </div>
      ) : null}
    </header>
  )
}
