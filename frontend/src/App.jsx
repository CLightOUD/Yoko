import { useEffect, useState } from 'react'
import { BarChart3, Bell, BookMarked, MessageCircle } from 'lucide-react'
import { getHealth } from './api/client'
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
    getHealth()
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
        {tab === 'chat' && <ChatPage />}
        {tab === 'reminders' && <RemindersPage />}
        {tab === 'memories' && <MemoriesPage />}
        {tab === 'metrics' && <MetricsPage />}
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