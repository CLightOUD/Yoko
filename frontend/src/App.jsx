import { useEffect, useState } from 'react'
import { Bell, BookMarked, LogOut, MessageCircle, Settings } from 'lucide-react'
import { getReadiness } from './api/client'
import { AUTH_STATUS } from './api/constants'
import { AuthProvider } from './auth/AuthContext'
import { useAuth } from './auth/useAuth'
import AuthPage from './pages/AuthPage'
import ChatPage from './pages/ChatPage'
import RemindersPage from './pages/RemindersPage'
import MemoriesPage from './pages/MemoriesPage'
import AccountPage from './pages/AccountPage'
import ReminderAlarm from './ReminderAlarm'
import './App.css'

const TABS = [
  { key: 'chat', label: '对话', icon: MessageCircle },
  { key: 'reminders', label: '提醒', icon: Bell },
  { key: 'memories', label: '记忆', icon: BookMarked },
  { key: 'account', label: '账户', icon: Settings },
]

function HealthBadge({ status }) {
  if (status === 'checking') {
    return (
      <span className="health">
        <span className="health__dot" aria-hidden="true" />
        连接中…
      </span>
    )
  }
  if (status === 'ok') {
    return (
      <span className="health">
        <span className="health__dot health__dot--ok" aria-hidden="true" />
        服务正常
      </span>
    )
  }
  return (
    <span className="health">
      <span className="health__dot health__dot--error" aria-hidden="true" />
      服务未连接
    </span>
  )
}

function StartupScreen() {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <img className="app-logo" src="/logo.svg" alt="渔歌" />
          <h1>Yoko 关怀助手</h1>
        </div>
        <p className="auth-hint">
          <span className="typing" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          正在恢复登录…
        </p>
      </div>
    </div>
  )
}

function SessionErrorScreen({ message, onRetry }) {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <img className="app-logo" src="/logo.svg" alt="渔歌" />
          <h1>Yoko 关怀助手</h1>
        </div>
        <div className="error-banner" role="alert">
          {message || '暂时无法确认登录状态，请稍后重试'}
        </div>
        <button className="btn auth-submit" type="button" onClick={onRetry}>
          重新连接
        </button>
      </div>
    </div>
  )
}

// 已登录后的主界面
function MainApp() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState('chat')
  const [health, setHealth] = useState('checking')
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState('')

  useEffect(() => {
    let alive = true
    getReadiness()
      .then((data) => {
        if (alive) setHealth(data.status === 'ok' ? 'ok' : 'error')
      })
      .catch(() => {
        if (alive) setHealth('error')
      })
    return () => {
      alive = false
    }
  }, [])

  async function handleLogout() {
    if (loggingOut) return
    setLogoutError('')
    setLoggingOut(true)
    try {
      await logout()
      setTab('chat')
    } catch (err) {
      setLogoutError(err?.message || '退出登录失败，请稍后重试')
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-brand">
          <img className="app-logo" src="/logo.svg" alt="渔歌" />
          <h1>Yoko 关怀助手</h1>
        </div>
        <div className="app-header-right">
          <HealthBadge status={health} />
          {user && (
            <button
              type="button"
              className="account-btn"
              onClick={handleLogout}
              disabled={loggingOut}
              title="退出登录"
            >
              <span className="account-btn__name">
                {user.display_name || user.username}
              </span>
              <LogOut aria-hidden="true" />
            </button>
          )}
        </div>
      </header>

      {logoutError && (
        <div className="app-notice">
          <div className="error-banner" role="alert">
            退出未完成：{logoutError}。您仍处于登录状态。
          </div>
        </div>
      )}

      <main className="app-main">
        {/* 保持所有页面挂载，仅用 display 控制显隐，避免切换 Tab 丢失状态 */}
        <div style={{ display: tab === 'chat' ? undefined : 'none' }}>
          <ChatPage key={user?.id ?? 'anonymous'} />
        </div>
        <div style={{ display: tab === 'reminders' ? undefined : 'none' }}>
          <RemindersPage />
        </div>
        <div style={{ display: tab === 'memories' ? undefined : 'none' }}>
          <MemoriesPage />
        </div>
        <div style={{ display: tab === 'account' ? undefined : 'none' }}>
          <AccountPage />
        </div>
      </main>

      <nav className="app-nav" aria-label="主导航">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            className={tab === key ? 'nav-item nav-item--active' : 'nav-item'}
            onClick={() => setTab(key)}
            aria-current={tab === key ? 'page' : undefined}
          >
            <Icon aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <ReminderAlarm />
    </div>
  )
}

function Gate() {
  const { status, error, restoreSession } = useAuth()
  if (status === AUTH_STATUS.LOADING) return <StartupScreen />
  if (status === AUTH_STATUS.ERROR) {
    return <SessionErrorScreen message={error} onRetry={restoreSession} />
  }
  if (status === AUTH_STATUS.UNAUTHENTICATED) return <AuthPage />
  return <MainApp />
}

function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}

export default App
