import { useEffect, useMemo, useRef, useState } from 'react'
import { History, Search, Send, X } from 'lucide-react'
import { sendChat } from '../api/client'
import {
  CHAT_STATUS,
  DEFAULT_TIMEZONE,
  MEMORY_ACTION_LABEL,
  TASK_TYPE_LABEL,
  TOOL_STATUS,
  USER_ID,
} from '../api/constants'
import { formatMs } from '../api/format'

let idCounter = 0
function nextId() {
  idCounter += 1
  return `msg-${Date.now()}-${idCounter}`
}

// 本地持久化：MVP 后端不保留历史会话，聊天记录存浏览器，保证刷新后仍可找回。
const STORAGE_KEY = `yoko.chat.${USER_ID}`
const MAX_HISTORY = 300

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : { messages: [], conversationId: null }
  } catch {
    return { messages: [], conversationId: null }
  }
}

function saveHistory(messages, conversationId) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ messages, conversationId }))
  } catch {
    // 存储已满或被禁用时静默忽略，不影响当前对话
  }
}

function AssistantBubble({ msg, highlighted }) {
  const isPartial = msg.status === CHAT_STATUS.PARTIAL
  const needsClarification = msg.status === CHAT_STATUS.NEEDS_CLARIFICATION
  const className = ['chat-bubble', 'chat-bubble--assistant']
  if (isPartial) className.push('chat-bubble--warning')
  if (needsClarification) className.push('chat-bubble--need-info')
  if (highlighted) className.push('chat-bubble--highlight')

  const usedMemories = (msg.memories ?? []).filter((m) => m.used)

  return (
    <div className={className.join(' ')}>
      <div>{msg.text}</div>

      {isPartial && (
        <div className="chat-meta">
          <span className="pill pill--red">部分操作未完成</span>
        </div>
      )}

      {needsClarification && (
        <div className="chat-meta">
          <span className="pill pill--info">还需要您补充一些信息</span>
        </div>
      )}

      {usedMemories.length > 0 && (
        <div className="chat-meta">
          <span className="chat-meta-label">使用了记忆：</span>
          {usedMemories.map((m) => (
            <span key={m.id} className="pill pill--green">
              {TASK_TYPE_LABEL[m.task_type] ?? m.task_type} · {m.display_text}
            </span>
          ))}
        </div>
      )}

      {(msg.tools ?? []).length > 0 && (
        <div className="chat-meta">
          <span className="chat-meta-label">操作：</span>
          {msg.tools.map((tool, index) => (
            <span
              key={index}
              className={
                tool.status === TOOL_STATUS.SUCCESS ? 'pill pill--green' : 'pill pill--red'
              }
            >
              {tool.summary}
            </span>
          ))}
        </div>
      )}

      {(msg.changes ?? []).length > 0 && (
        <div className="chat-meta">
          <span className="chat-meta-label">已记住，可撤销：</span>
          {msg.changes.map((change, index) => (
            <span key={index} className="pill pill--amber">
              {MEMORY_ACTION_LABEL[change.action]}：
              {change.memory ? change.memory.display_text : change.reason}
            </span>
          ))}
        </div>
      )}

      {msg.metrics && (
        <div className="chat-meta">
          <span className="pill pill--gray">本次耗时 {formatMs(msg.metrics.total_ms)}</span>
        </div>
      )}
    </div>
  )
}

function HistoryPanel({ open, onClose, onSelect }) {
  const [query, setQuery] = useState('')
  const history = useMemo(
    () => (open ? loadHistory() : { messages: [], conversationId: null }),
    [open],
  )

  const all = useMemo(() => {
    const messages = (history.messages ?? []).flatMap((m) => m)
    return [...messages].sort((a, b) => (b.time ?? 0) - (a.time ?? 0))
  }, [history])

  const results = useMemo(() => {
    const keyword = query.trim().toLocaleLowerCase()
    if (!keyword) return all
    return all.filter((m) =>
      (m.text ?? '').toLocaleLowerCase().includes(keyword),
    )
  }, [all, query])

  if (!open) return null

  return (
    <div className="history-overlay" role="dialog" aria-modal="true" aria-label="历史记录">
      <div className="history-panel">
        <div className="history-head">
          <h2 className="history-title">
            <History aria-hidden="true" />
            <span>历史记录</span>
          </h2>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="关闭历史记录"
          >
            <X aria-hidden="true" />
          </button>
        </div>

        <div className="history-search">
          <Search className="history-search__icon" aria-hidden="true" />
          <input
            className="field history-search__input"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入关键词查找过往对话"
            aria-label="搜索历史记录"
          />
        </div>

        {results.length === 0 ? (
          <p className="empty">
            {query.trim() ? '没有找到相关记录' : '还没有历史对话'}
          </p>
        ) : (
          <ul className="history-list">
            {results.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  className="history-item"
                  onClick={() => onSelect(m)}
                >
                  <span className={`history-item__role history-item__role--${m.role}`}>
                    {m.role === 'user' ? '我' : 'Yoko'}
                  </span>
                  <span className="history-item__text">{m.text}</span>
                  {m.time ? (
                    <span className="history-item__time">
                      {new Date(m.time).toLocaleString('zh-CN', {
                        month: 'numeric',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [highlightId, setHighlightId] = useState(null)
  const listEndRef = useRef(null)

  // 惰性恢复上次会话
  useEffect(() => {
    const stored = loadHistory()
    if (stored.messages?.length) setMessages(stored.messages)
    if (stored.conversationId) setConversationId(stored.conversationId)
  }, [])

  // 持久化到本地
  useEffect(() => {
    if (messages.length) saveHistory(messages, conversationId)
  }, [messages, conversationId])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setError('')
    setMessages((prev) => [
      ...prev.slice(-MAX_HISTORY + 1),
      { id: nextId(), role: 'user', text, time: Date.now() },
    ])
    setLoading(true)

    try {
      const res = await sendChat({
        user_id: USER_ID,
        conversation_id: conversationId,
        message: text,
        timezone: DEFAULT_TIMEZONE,
      })
      setConversationId(res.conversation_id)
      setMessages((prev) => [
        ...prev.slice(-MAX_HISTORY + 1),
        {
          id: nextId(),
          role: 'assistant',
          text: res.reply,
          time: Date.now(),
          status: res.status,
          memories: res.retrieved_memories,
          tools: res.tool_calls,
          changes: res.memory_changes,
          metrics: res.metrics,
        },
      ])
    } catch (err) {
      setError(err.message || '发送失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  // 点击历史记录：若仍在当前加载列表，滚动定位并高亮；否则回填到输入框
  function handleSelectHistory(item) {
    setHistoryOpen(false)
    if (messages.some((m) => m.id === item.id)) {
      setHighlightId(item.id)
      requestAnimationFrame(() => {
        document.getElementById(`anchor-${item.id}`)?.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        })
      })
    } else {
      setInput(item.text ?? '')
    }
  }

  return (
    <div className="page">
      <div className="chat-toolbar">
        <button
          type="button"
          className="btn btn--secondary btn--small"
          onClick={() => setHistoryOpen(true)}
        >
          <History aria-hidden="true" />
          历史记录
        </button>
      </div>

      <div className="chat-list" aria-live="polite">
        {messages.length === 0 && (
          <p className="empty">
            您好，我是 Yoko。您可以让我设置提醒，例如“明天晚上7点提醒我吃药”。
          </p>
        )}
        {messages.map((msg) =>
          msg.role === 'user' ? (
            <div
              key={msg.id}
              id={`anchor-${msg.id}`}
              className="chat-bubble chat-bubble--user"
            >
              {msg.text}
            </div>
          ) : (
            <div key={msg.id} id={`anchor-${msg.id}`}>
              <AssistantBubble msg={msg} highlighted={highlightId === msg.id} />
            </div>
          ),
        )}
        {loading && (
          <div
            className="chat-bubble chat-bubble--assistant chat-bubble--pending"
            aria-live="polite"
          >
            <span className="typing" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            Yoko 正在思考…
          </div>
        )}
        <div ref={listEndRef} />
      </div>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <div className="composer">
        <textarea
          rows={1}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="请输入消息，例如：明天晚上7点提醒我吃药"
          aria-label="消息输入框"
        />
        <button
          className="btn"
          type="button"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          <Send aria-hidden="true" />
          {loading ? '发送中…' : '发送'}
        </button>
      </div>

      <HistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onSelect={handleSelectHistory}
      />
    </div>
  )
}
