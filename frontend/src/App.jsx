import { useEffect, useState } from 'react'
import { BarChart3, Bell, BookMarked, LogOut, MessageCircle } from 'lucide-react'
import { getReadiness } from './api/client'
import { AUTH_STATUS } from './api/constants'
import { AuthProvider, useAuth } from './auth/AuthContext'
import AuthPage from './pages/AuthPage'
import ChatPage from './pages/ChatPage'
import RemindersPage from './pages/RemindersPage'
import MemoriesPage from './pages/MemoriesPage'
import MetricsPage from './pages/MetricsPage'
import ReminderAlarm from './ReminderAlarm'
import './App.css'

const TABS = [
  { key: 'chat', label: '对话', icon: MessageCircle },
  { key: 'reminders', label: '提醒', icon: Bell },
  { key: 'memories', label: '记忆', icon: BookMarked },
  { key: 'metrics', label: '指标', icon: BarChart3 },
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

// 已登录后的主界面
function MainApp() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState('chat')
  const [health, setHealth] = useState('checking')
  const [loggingOut, setLoggingOut] = useState(false)

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
    setLoggingOut(true)
    // logout 内部无论成功失败都会清除认证状态并回到登录页
    await logout().catch(() => {})
    setTab('chat')
    setLoggingOut(false)
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

      <main className="app-main">
        {/* 保持所有页面挂载，仅用 display 控制显隐，避免切换 Tab 丢失状态 */}
        <div style={{ display: tab === 'chat' ? undefined : 'none' }}>
          <ChatPage />
        </div>
        <div style={{ display: tab === 'reminders' ? undefined : 'none' }}>
          <RemindersPage />
        </div>
        <div style={{ display: tab === 'memories' ? undefined : 'none' }}>
          <MemoriesPage />
        </div>
        <div style={{ display: tab === 'metrics' ? undefined : 'none' }}>
          <MetricsPage />
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
  const { status } = useAuth()
  if (status === AUTH_STATUS.LOADING) return <StartupScreen />
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