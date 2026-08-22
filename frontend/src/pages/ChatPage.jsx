import { useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
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

function AssistantBubble({ msg }) {
  const isPartial = msg.status === CHAT_STATUS.PARTIAL
  const className = isPartial
    ? 'chat-bubble chat-bubble--assistant chat-bubble--warning'
    : 'chat-bubble chat-bubble--assistant'

  const usedMemories = (msg.memories ?? []).filter((m) => m.used)

  return (
    <div className={className}>
      <div>{msg.text}</div>

      {isPartial && (
        <div className="chat-meta">
          <span className="pill pill--red">部分操作未完成</span>
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
          <span className="pill pill--gray">
            本次耗时 {formatMs(msg.metrics.total_ms)}
          </span>
        </div>
      )}
    </div>
  )
}

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const listEndRef = useRef(null)

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setError('')
    setMessages((prev) => [...prev, { id: nextId(), role: 'user', text }])
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
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          text: res.reply,
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

  return (
    <div className="page">
      <div className="chat-list" aria-live="polite">
        {messages.length === 0 && (
          <p className="empty">
            您好，我是 Yoko。您可以让我设置提醒，例如“明天晚上7点提醒我吃药”。
          </p>
        )}
        {messages.map((msg) =>
          msg.role === 'user' ? (
            <div key={msg.id} className="chat-bubble chat-bubble--user">
              {msg.text}
            </div>
          ) : (
            <AssistantBubble key={msg.id} msg={msg} />
          ),
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
    </div>
  )
}