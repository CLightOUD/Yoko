import { useCallback, useEffect, useState } from 'react'
import { Plus, RefreshCw, Trash2 } from 'lucide-react'
import {
  createReminder,
  deleteReminder,
  listReminders,
} from '../api/client'
import {
  DEFAULT_TIMEZONE,
  REMINDER_STATUS,
  REMINDER_STATUS_LABEL,
  REPEAT_TYPE,
  REPEAT_TYPE_LABEL,
  USER_ID,
} from '../api/constants'
import { formatFullDateTime, localToIso } from '../api/format'

function CreateReminderForm({ onCreated }) {
  const [title, setTitle] = useState('')
  const [triggerAt, setTriggerAt] = useState('')
  const [repeatType, setRepeatType] = useState(REPEAT_TYPE.NONE)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')

    if (!title.trim() || !triggerAt) {
      setError('请填写提醒内容和时间')
      return
    }

    setSubmitting(true)
    try {
      await createReminder({
        user_id: USER_ID,
        title: title.trim(),
        next_trigger_at: localToIso(triggerAt),
        timezone: DEFAULT_TIMEZONE,
        repeat_type: repeatType,
      })
      setTitle('')
      setTriggerAt('')
      setRepeatType(REPEAT_TYPE.NONE)
      onCreated()
    } catch (err) {
      setError(err.message || '创建失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">新建提醒</h2>
      <form className="form-group" onSubmit={handleSubmit}>
        <div className="form-row">
          <label htmlFor="reminder-title">提醒内容</label>
          <input
            id="reminder-title"
            className="field"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="例如：服用降压药"
            maxLength={200}
          />
        </div>
        <div className="form-row">
          <label htmlFor="reminder-time">提醒时间</label>
          <input
            id="reminder-time"
            className="field"
            type="datetime-local"
            value={triggerAt}
            onChange={(event) => setTriggerAt(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="reminder-repeat">重复周期</label>
          <select
            id="reminder-repeat"
            className="field"
            value={repeatType}
            onChange={(event) => setRepeatType(event.target.value)}
          >
            <option value={REPEAT_TYPE.NONE}>{REPEAT_TYPE_LABEL[REPEAT_TYPE.NONE]}</option>
            <option value={REPEAT_TYPE.DAILY}>{REPEAT_TYPE_LABEL[REPEAT_TYPE.DAILY]}</option>
            <option value={REPEAT_TYPE.WEEKLY}>{REPEAT_TYPE_LABEL[REPEAT_TYPE.WEEKLY]}</option>
          </select>
        </div>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        <button className="btn" type="submit" disabled={submitting}>
          <Plus aria-hidden="true" />
          {submitting ? '创建中…' : '创建提醒'}
        </button>
      </form>
    </div>
  )
}

export default function RemindersPage() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await listReminders({ user_id: USER_ID, status: REMINDER_STATUS.ACTIVE })
      setItems(res.items)
      setTotal(res.total)
    } catch (err) {
      setError(err.message || '加载提醒失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleDelete(id, title) {
    const confirmed = window.confirm(`确定要删除“${title}”这个提醒吗？`)
    if (!confirmed) return
    try {
      await deleteReminder(id, USER_ID)
      load()
    } catch (err) {
      setError(err.message || '删除失败，请重试')
    }
  }

  return (
    <div className="page">
      <div className="page-actions">
        <h1 className="page-title">提醒</h1>
        <button
          className="btn btn--secondary btn--small"
          type="button"
          onClick={load}
          disabled={loading}
        >
          <RefreshCw aria-hidden="true" />
          刷新
        </button>
      </div>

      <CreateReminderForm onCreated={load} />

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="empty">正在加载…</p>
      ) : items.length === 0 ? (
        <p className="empty">暂无进行中的提醒</p>
      ) : (
        <div className="card">
          <h2 className="section-title">进行中的提醒（{total}）</h2>
          {items.map((reminder) => (
            <div key={`${reminder.id}-${reminder.next_trigger_at}`} className="list-item">
              <div className="list-item__row">
                <span className="list-item__title">{reminder.title}</span>
                <span className="pill">{REPEAT_TYPE_LABEL[reminder.repeat_type]}</span>
                <span className="pill pill--green">
                  {REMINDER_STATUS_LABEL[reminder.status]}
                </span>
              </div>
              <div className="list-item__sub">
                下次提醒：{formatFullDateTime(reminder.next_trigger_at)}
              </div>
              <div className="list-item__row">
                <button
                  className="btn btn--danger btn--small"
                  type="button"
                  onClick={() => handleDelete(reminder.id, reminder.title)}
                >
                  <Trash2 aria-hidden="true" />
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}