import { useEffect, useState } from 'react'
import { BarChart3, Bell, BookMarked, MessageCircle } from 'lucide-react'
import { getReadiness } from './api/client'
import ChatPage from './pages/ChatPage'
import RemindersPage from './pages/RemindersPage'
import MemoriesPage from './pages/MemoriesPage'
import MetricsPage from './pages/MetricsPage'
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

function App() {
  const [tab, setTab] = useState('chat')
  const [health, setHealth] = useState('checking')

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

  return (
    <div className="app">
      <header className="app-header">
        <h1>Yoko 关怀助手</h1>
        <HealthBadge status={health} />
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
    </div>
  )
}

export default App
