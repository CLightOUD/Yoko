import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  History,
  Plus,
  RefreshCw,
  Search,
  Send,
  ThumbsDown,
  ThumbsUp,
  X,
  Download,
  Trash2,
  ExternalLink,
  Clock,
  ImagePlus,
} from 'lucide-react'
import { sendChat, sendFeedback } from '../api/client'
import {
  CHAT_STATUS,
  ERROR_CODE,
  FEEDBACK_RATING,
  MEMORY_ACTION_LABEL,
  TASK_TYPE_LABEL,
  TOOL_STATUS,
} from '../api/constants'
import { useAuth } from '../auth/useAuth'
import { formatMs } from '../api/format.js'
import {
  MAX_CHAT_HISTORY,
  archiveConversation,
  clearChatHistory,
  loadChatHistory,
  saveChatHistory,
} from '../chatStorage.js'
import { validateImageFile, fileToBase64, fileToPreviewUrl } from '../utils/imageUtils.js'

let idCounter = 0
function nextId() {
  idCounter += 1
  return `msg-${Date.now()}-${idCounter}`
}

function exportChatHistory(userId, messages) {
  const data = {
    exported_at: new Date().toISOString(),
    user_id: userId,
    message_count: messages.length,
    messages: messages.map((m) => ({
      role: m.role,
      text: m.text,
      time: m.time ? new Date(m.time).toISOString() : null,
      status: m.status ?? null,
    })),
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `yoko-chat-${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// ===== Sources 引用展示 =====
function SourceCitations({ sources }) {
  if (!sources?.length) return null
  return (
    <div className="chat-meta chat-sources">
      <span className="chat-meta-label">参考来源：</span>
      <ol className="source-list">
        {sources.map((s, i) => (
          <li key={i} className="source-item">
            <a
              href={s.url}
              target="_blank"
              rel="noopener noreferrer"
              className="source-link"
              title={s.snippet || s.title}
            >
              <span className="source-index">[{i + 1}]</span>
              <span className="source-title">{s.title || s.url}</span>
              <ExternalLink aria-hidden="true" size={14} />
            </a>
          </li>
        ))}
      </ol>
    </div>
  )
}

// ===== 反馈组件：点赞、点踩、反馈原因 =====
function FeedbackBar({ msg, onSubmit }) {
  const [rating, setRating] = useState(msg.feedback?.rating ?? null)
  const [showReason, setShowReason] = useState(false)
  const [reasonText, setReasonText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(!!msg.feedback?.submitted)

  const requestId = msg.request_id
  if (!requestId) return null

  async function handleRating(nextRating) {
    if (submitting || submitted) return
    // 再次点击相同评分取消
    const target = rating === nextRating ? null : nextRating
    setRating(target)
    if (target === FEEDBACK_RATING.DOWN) {
      setShowReason(true)
      setError('')
    } else {
      setShowReason(false)
      if (target) {
        // 点赞直接提交
        await doSubmit(target, '')
      }
    }
  }

  async function doSubmit(ratingValue, feedbackText) {
    if (!requestId || submitting) return
    setSubmitting(true)
    setError('')
    try {
      await onSubmit({
        request_id: requestId,
        rating: ratingValue,
        feedback_text: feedbackText || null,
      })
      setSubmitted(true)
    } catch (err) {
      setError(err?.message || '反馈提交失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleReasonSubmit() {
    const text = reasonText.trim()
    if (!rating || submitting) return
    await doSubmit(rating, text)
  }

  return (
    <div className="chat-feedback">
      <div className="chat-feedback__actions">
        <button
          type="button"
          className={`icon-btn icon-btn--feedback ${rating === FEEDBACK_RATING.UP ? 'is-active' : ''}`}
          onClick={() => handleRating(FEEDBACK_RATING.UP)}
          disabled={submitting || submitted}
          title="有帮助"
          aria-label="点赞"
        >
          <ThumbsUp size={16} aria-hidden="true" />
        </button>
        <button
          type="button"
          className={`icon-btn icon-btn--feedback ${rating === FEEDBACK_RATING.DOWN ? 'is-active' : ''}`}
          onClick={() => handleRating(FEEDBACK_RATING.DOWN)}
          disabled={submitting || submitted}
          title="没帮助"
          aria-label="点踩"
        >
          <ThumbsDown size={16} aria-hidden="true" />
        </button>
        {submitted && <span className="feedback-submitted">已反馈</span>}
      </div>

      {showReason && !submitted && (
        <div className="feedback-reason">
          <textarea
            className="field feedback-reason__input"
            rows={2}
            value={reasonText}
            onChange={(e) => setReasonText(e.target.value)}
            placeholder="可以告诉我们哪里不对吗？（可选）"
            maxLength={500}
          />
          <div className="feedback-reason__actions">
            {error && <span className="feedback-error">{error}</span>}
            <button
              type="button"
              className="btn btn--secondary btn--small"
              onClick={() => {
                setShowReason(false)
                setRating(null)
                setReasonText('')
                setError('')
              }}
              disabled={submitting}
            >
              取消
            </button>
            <button
              type="button"
              className="btn btn--small"
              onClick={handleReasonSubmit}
              disabled={submitting}
            >
              {submitting ? '提交中…' : '提交反馈'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function AssistantBubble({ msg, highlighted, onFeedback }) {
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
              key={`${tool.tool_name}-${index}`}
              className={
                tool.status === TOOL_STATUS.SUCCESS
                  ? 'pill pill--green'
                  : 'pill pill--red'
              }
            >
              {tool.summary}
            </span>
          ))}
        </div>
      )}

      <SourceCitations sources={msg.sources} />

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
            耗时 {formatMs(msg.metrics.total_ms)}
          </span>
          <span className="pill pill--gray">
            模型调用 {msg.metrics.model_call_count} 次
          </span>
          {msg.metrics.input_tokens != null && msg.metrics.output_tokens != null && (
            <span className="pill pill--gray">
              Token {msg.metrics.input_tokens} + {msg.metrics.output_tokens}
            </span>
          )}
          {msg.metrics.memory_tokens > 0 && (
            <span className="pill pill--gray">
              记忆 Token {msg.metrics.memory_tokens}
            </span>
          )}
        </div>
      )}

      <FeedbackBar msg={msg} onSubmit={onFeedback} />
    </div>
  )
}

function HistoryPanel({ open, onClose, onSelect, onNewChat, onClear, onExport, messages, busy }) {
  const [query, setQuery] = useState('')

  const all = useMemo(() => {
    return [...messages].sort((a, b) => (b.time ?? 0) - (a.time ?? 0))
  }, [messages])

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

        <div className="history-actions">
          <button
            type="button"
            className="btn btn--secondary btn--small"
            onClick={onNewChat}
            disabled={busy}
          >
            <Plus aria-hidden="true" />
            新对话
          </button>
          <button
            type="button"
            className="btn btn--secondary btn--small"
            onClick={onExport}
          >
            <Download aria-hidden="true" />
            导出记录
          </button>
          <button
            type="button"
            className="btn btn--danger btn--small"
            onClick={onClear}
            disabled={busy}
          >
            <Trash2 aria-hidden="true" />
            清空本地
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

// 根据错误状态码生成用户友好的提示和操作建议
function getErrorDisplay(error) {
  if (!error) return null
  const status = error?.status
  const code = error?.code

  if (status === 401) {
    return { type: 'auth', text: '登录已过期，请重新登录后再试。' }
  }
  if (status === 409 || code === ERROR_CODE.RESOURCE_CONFLICT) {
    return {
      type: 'conflict',
      text: '请求与当前状态冲突，可能内容已被修改。请刷新后重试。',
    }
  }
  if (status === 429 || code === ERROR_CODE.TOO_MANY_ATTEMPTS) {
    const secs = error?.retryAfter
    return {
      type: 'rate',
      text: secs
        ? `请求过于频繁，请 ${secs} 秒后再试。`
        : '请求过于频繁，请稍后再试。',
      retryAfter: secs ?? null,
    }
  }
  if (status === 503) {
    return {
      type: 'unavailable',
      text: '服务暂时不可用，请稍后重试。',
    }
  }
  if (status === 502) {
    return {
      type: 'model',
      text: error?.message || '模型暂时无法响应，请稍后重试。',
    }
  }
  if (status === 0 && error?.message?.includes('超时')) {
    return { type: 'timeout', text: error.message }
  }
  return { type: 'general', text: error?.message || '发送失败，请重试' }
}

export default function ChatPage() {
  const { user } = useAuth()
  const userId = user?.id ?? 'anonymous'
  const timezone = user?.timezone ?? null

  const [messages, setMessages] = useState([])
  const [archivedMessages, setArchivedMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [retryRequest, setRetryRequest] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [highlightId, setHighlightId] = useState(null)
  const [rateCountdown, setRateCountdown] = useState(null)
  const [selectedImage, setSelectedImage] = useState(null)
  const [imagePreviewUrl, setImagePreviewUrl] = useState(null)
  const [imageError, setImageError] = useState(null)

  const listEndRef = useRef(null)
  const abortRef = useRef(null)
  const rateTimerRef = useRef(null)
  const fileInputRef = useRef(null)

  // 惰性恢复上次会话
  useEffect(() => {
    const stored = loadChatHistory(userId)
    setMessages(stored.messages ?? [])
    setArchivedMessages(stored.archivedMessages ?? [])
    setConversationId(stored.conversationId ?? null)
  }, [userId])

  // 持久化到本地
  useEffect(() => {
    if (messages.length || archivedMessages.length || conversationId) {
      saveChatHistory(userId, { messages, archivedMessages, conversationId })
    }
  }, [userId, messages, archivedMessages, conversationId])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 限流倒计时
  useEffect(() => {
    if (rateCountdown == null) return
    if (rateCountdown <= 0) {
      setRateCountdown(null)
      return
    }
    rateTimerRef.current = setTimeout(() => {
      setRateCountdown((prev) => (prev == null ? null : Math.max(0, prev - 1)))
    }, 1000)
    return () => clearTimeout(rateTimerRef.current)
  }, [rateCountdown])

  const submitChat = useCallback(async (request, { appendUser, image }) => {
    setError(null)
    setImageError(null)
    if (appendUser) {
      setMessages((prev) => [
        ...prev.slice(-MAX_CHAT_HISTORY + 1),
        {
          id: nextId(),
          role: 'user',
          text: request.text,
          time: Date.now(),
          imagePreviewUrl: image?.previewUrl ?? null,
          imageFileName: image?.fileName ?? null,
        },
      ])
    }
    setLoading(true)

    try {
      const res = await sendChat({
        conversation_id: request.conversationId,
        message: request.text,
        timezone,
        idempotency_key: request.idempotencyKey,
        image: image
          ? {
              media_type: image.mediaType,
              data: image.base64,
              detail: 'original',
            }
          : null,
      })
      setRetryRequest(null)
      setConversationId(res.conversation_id)
      setMessages((prev) => [
        ...prev.slice(-MAX_CHAT_HISTORY + 1),
        {
          id: nextId(),
          role: 'assistant',
          text: res.reply,
          time: Date.now(),
          status: res.status,
          memories: res.retrieved_memories,
          tools: res.tool_calls,
          sources: res.sources,
          changes: res.memory_changes,
          metrics: res.metrics,
          request_id: res.request_id,
          feedback: {},
        },
      ])
      // 发送成功后清空图片
      setSelectedImage(null)
      setImagePreviewUrl(null)
      if (image?.previewUrl) {
        URL.revokeObjectURL(image.previewUrl)
      }
    } catch (err) {
      const errInfo = getErrorDisplay(err)
      setError(errInfo)
      setRetryRequest(request)
      if (err?.status === 429 && err?.retryAfter != null) {
        setRateCountdown(err.retryAfter)
      }
    } finally {
      setLoading(false)
      abortRef.current = null
    }
  }, [timezone])

  async function handleSend() {
    const text = input.trim()
    const hasImage = selectedImage != null
    if ((!text && !hasImage) || loading) return
    if (rateCountdown != null && rateCountdown > 0) return

    // 先进行 Base64 转换（可能耗时），转换期间禁用输入
    let imageInfo = null
    if (hasImage) {
      try {
        const base64 = await fileToBase64(selectedImage)
        imageInfo = {
          mediaType: selectedImage.type,
          base64,
          previewUrl: imagePreviewUrl,
          fileName: selectedImage.name,
        }
      } catch {
        setImageError('图片编码失败，请重试')
        return
      }
    }

    const request = {
      text,
      conversationId,
      idempotencyKey: crypto.randomUUID(),
      imageInfo,
    }
    setInput('')
    setRetryRequest(null)
    setError(null)
    setImageError(null)

    submitChat(request, { appendUser: true, image: imageInfo })
  }

  function handleRetry() {
    if (!retryRequest || loading) return
    // 重试时不需要重新转 Base64——图片已在 handleSend 时转换
    const imageInfo = retryRequest.imageInfo ?? null
    submitChat(retryRequest, { appendUser: false, image: imageInfo })
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  function handleImageSelect(event) {
    const file = event.target.files?.[0]
    if (!file) return

    const result = validateImageFile(file)
    if (!result.valid) {
      setImageError(result.error)
      return
    }

    setImageError(null)
    fileToPreviewUrl(file).then((url) => {
      setSelectedImage(file)
      setImagePreviewUrl(url)
    }).catch(() => {
      setImageError('图片预览加载失败')
    })
  }

  function handleRemoveImage() {
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl)
    }
    setSelectedImage(null)
    setImagePreviewUrl(null)
    setImageError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
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

  function handleNewChat() {
    if (loading) return
    const confirmed = messages.length === 0 || window.confirm('开始新对话将清空当前对话视图（本地记录仍保留）。是否继续？')
    if (!confirmed) return
    setArchivedMessages((prev) => archiveConversation(prev, messages))
    setMessages([])
    setConversationId(null)
    setError(null)
    setRetryRequest(null)
    setHistoryOpen(false)
  }

  function handleClearHistory() {
    if (loading) return
    const confirmed = window.confirm('确定要清空本地所有聊天记录吗？此操作不可恢复。')
    if (!confirmed) return
    clearChatHistory(userId)
    setMessages([])
    setArchivedMessages([])
    setConversationId(null)
    setError(null)
    setRetryRequest(null)
    setHistoryOpen(false)
  }

  function handleExportHistory() {
    exportChatHistory(userId, [...archivedMessages, ...messages])
  }

  async function handleFeedback({ request_id, rating, feedback_text }) {
    const res = await sendFeedback({ request_id, rating, feedback_text })
    // 标记已提交，并更新记忆变化展示
    setMessages((prev) =>
      prev.map((m) =>
        m.request_id === request_id
          ? {
              ...m,
              feedback: { rating, submitted: true },
              changes: res?.memory_changes?.length
                ? [...(m.changes ?? []), ...res.memory_changes]
                : m.changes,
            }
          : m,
      ),
    )
    return res
  }

  const errorDisplay = error

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
        <button
          type="button"
          className="btn btn--secondary btn--small"
          onClick={handleNewChat}
          disabled={loading}
          title="开始新的对话"
        >
          <Plus aria-hidden="true" />
          新对话
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
              {msg.imagePreviewUrl && (
                <div className="chat-image-preview">
                  <img
                    src={msg.imagePreviewUrl}
                    alt={msg.imageFileName || '图片'}
                    className="chat-image-preview__img"
                  />
                  {msg.imageFileName && (
                    <span className="chat-image-preview__name">{msg.imageFileName}</span>
                  )}
                </div>
              )}
              {msg.text}
            </div>
          ) : (
            <div key={msg.id} id={`anchor-${msg.id}`}>
              <AssistantBubble
                msg={msg}
                highlighted={highlightId === msg.id}
                onFeedback={handleFeedback}
              />
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

      {errorDisplay && (
        <div
          className={`error-banner error-banner--action ${
            errorDisplay.type === 'rate' ? 'error-banner--rate' : ''
          }`}
          role="alert"
        >
          <span>
            {errorDisplay.type === 'rate' && rateCountdown != null && rateCountdown > 0 ? (
              <>
                <Clock aria-hidden="true" size={14} />
                <span>限流中，{rateCountdown} 秒后可重试</span>
              </>
            ) : (
              errorDisplay.text
            )}
          </span>
          {retryRequest && errorDisplay.type !== 'auth' && (
            <button
              className="btn btn--secondary btn--small"
              type="button"
              onClick={handleRetry}
              disabled={loading || (rateCountdown != null && rateCountdown > 0)}
            >
              <RefreshCw aria-hidden="true" />
              {loading ? '重试中…' : '重试发送'}
            </button>
          )}
        </div>
      )}

      {imageError && (
        <div className="error-banner" role="alert">
          {imageError}
        </div>
      )}

      {imagePreviewUrl && selectedImage && (
        <div className="composer-image-preview">
          <img
            src={imagePreviewUrl}
            alt={selectedImage.name}
            className="composer-image-preview__img"
          />
          <div className="composer-image-preview__info">
            <span className="composer-image-preview__name">{selectedImage.name}</span>
            <span className="composer-image-preview__size">
              {(selectedImage.size / 1024).toFixed(0)} KiB
            </span>
          </div>
          <button
            type="button"
            className="icon-btn composer-image-preview__remove"
            onClick={handleRemoveImage}
            aria-label="移除图片"
            disabled={loading}
          >
            <X aria-hidden="true" size={18} />
          </button>
        </div>
      )}

      <div className="composer">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          onChange={handleImageSelect}
          className="composer__file-input"
          tabIndex={-1}
          aria-hidden="true"
        />
        <button
          type="button"
          className="icon-btn composer__image-btn"
          onClick={() => fileInputRef.current?.click()}
          disabled={loading || (rateCountdown != null && rateCountdown > 0)}
          title="添加图片"
          aria-label="添加图片"
        >
          <ImagePlus aria-hidden="true" size={22} />
        </button>
        <textarea
          rows={1}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="请输入消息，例如：明天晚上7点提醒我吃药"
          aria-label="消息输入框"
          disabled={loading || (rateCountdown != null && rateCountdown > 0)}
        />
        <button
          className="btn"
          type="button"
          onClick={handleSend}
          disabled={loading || (!input.trim() && !selectedImage) || (rateCountdown != null && rateCountdown > 0)}
        >
          <Send aria-hidden="true" />
          {loading ? '发送中…' : '发送'}
        </button>
      </div>

      <HistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onSelect={handleSelectHistory}
        onNewChat={handleNewChat}
        onClear={handleClearHistory}
        onExport={handleExportHistory}
        messages={[...archivedMessages, ...messages]}
        busy={loading}
      />
    </div>
  )
}
