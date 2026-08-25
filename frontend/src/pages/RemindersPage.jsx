import { useCallback, useEffect, useState } from 'react'
import { Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import {
  createReminder,
  deleteReminder,
  listReminders,
  updateReminder,
} from '../api/client'
import {
  DEFAULT_TIMEZONE,
  REMINDER_LIST_STATUS,
  REMINDER_STATUS,
  REMINDER_STATUS_LABEL,
  REPEAT_TYPE,
  REPEAT_TYPE_LABEL,
} from '../api/constants'
import { formatFullDateTime, isoToLocalInput, localToIso } from '../api/format'
import { useAuth } from '../auth/useAuth'

const FILTERS = [
  { key: REMINDER_LIST_STATUS.ACTIVE, label: '进行中' },
  { key: REMINDER_LIST_STATUS.COMPLETED, label: '已完成' },
  { key: REMINDER_LIST_STATUS.ALL, label: '全部' },
]

function CreateReminderForm({ onCreated, timezone }) {
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
    const nextTriggerAt = localToIso(triggerAt, timezone)
    if (!nextTriggerAt) {
      setError('这个时间在当前时区无效，请重新选择')
      return
    }

    setSubmitting(true)
    try {
      await createReminder({
        title: title.trim(),
        next_trigger_at: nextTriggerAt,
        timezone,
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

function EditReminderForm({ reminder, onCancel, onSaved, timezone }) {
  const [title, setTitle] = useState(reminder.title ?? '')
  const [triggerAt, setTriggerAt] = useState(isoToLocalInput(reminder.next_trigger_at, timezone))
  const [repeatType, setRepeatType] = useState(reminder.repeat_type ?? REPEAT_TYPE.NONE)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')

    if (!title.trim() || !triggerAt) {
      setError('请填写提醒内容和时间')
      return
    }
    const nextTriggerAt = localToIso(triggerAt, timezone)
    if (!nextTriggerAt) {
      setError('这个时间在当前时区无效，请重新选择')
      return
    }
    if (new Date(nextTriggerAt).getTime() <= Date.now()) {
      setError('修改后的提醒时间需晚于当前时间')
      return
    }

    setSubmitting(true)
    try {
      await updateReminder(reminder.id, {
        title: title.trim(),
        next_trigger_at: nextTriggerAt,
        timezone,
        repeat_type: repeatType,
      })
      onSaved()
    } catch (err) {
      setError(err.message || '保存失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="card inv edit-card">
      <h3 className="section-title">修改提醒</h3>
      <form className="form-group" onSubmit={handleSubmit}>
        <div className="form-row">
          <label htmlFor={`edit-title-${reminder.id}`}>提醒内容</label>
          <input
            id={`edit-title-${reminder.id}`}
            className="field"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={200}
          />
        </div>
        <div className="form-row">
          <label htmlFor={`edit-time-${reminder.id}`}>提醒时间</label>
          <input
            id={`edit-time-${reminder.id}`}
            className="field"
            type="datetime-local"
            value={triggerAt}
            onChange={(event) => setTriggerAt(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor={`edit-repeat-${reminder.id}`}>重复周期</label>
          <select
            id={`edit-repeat-${reminder.id}`}
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
        <div className="btn-row">
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? '保存中…' : '保存'}
          </button>
          <button
            className="btn btn--secondary"
            type="button"
            onClick={onCancel}
            disabled={submitting}
          >
            取消
          </button>
        </div>
      </form>
    </div>
  )
}

export default function RemindersPage() {
  const { user } = useAuth()
  const timezone = user?.timezone || DEFAULT_TIMEZONE
  const [items, setItems] = useState([])
  const [filter, setFilter] = useState(REMINDER_LIST_STATUS.ACTIVE)
  const [editingId, setEditingId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await listReminders({ status: filter })
      setItems(res.items)
    } catch (err) {
      setError(err.message || '加载提醒失败')
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    load()
  }, [load])

  // “全部”会包含已删除项，展示时隐藏，避免用户看到删除的提醒。
  const visible = items.filter((r) => r.status !== REMINDER_STATUS.DELETED)

  async function handleDelete(id, title) {
    const confirmed = window.confirm(`确定要删除“${title}”这个提醒吗？`)
    if (!confirmed) return
    try {
      await deleteReminder(id)
      load()
    } catch (err) {
      setError(err.message || '删除失败，请重试')
    }
  }

  const activeFilterLabel =
    FILTERS.find((f) => f.key === filter)?.label ?? ''

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

      <div className="filter-tabs" role="group" aria-label="按状态筛选提醒">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`filter-tab${filter === f.key ? ' filter-tab--active' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <CreateReminderForm onCreated={load} timezone={timezone} />

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="empty">正在加载…</p>
      ) : visible.length === 0 ? (
        <p className="empty">暂无{activeFilterLabel}的提醒</p>
      ) : (
        <div className="card">
          <h2 className="section-title">
            {activeFilterLabel}的提醒（{visible.length}）
          </h2>
          {visible.map((reminder) => (
            <div
              key={`${reminder.id}-${reminder.next_trigger_at}`}
              className="list-item"
            >
              {editingId === reminder.id ? (
                <EditReminderForm
                  reminder={reminder}
                  onCancel={() => setEditingId(null)}
                  onSaved={() => {
                    setEditingId(null)
                    load()
                  }}
                  timezone={timezone}
                />
              ) : (
                <>
                  <div className="list-item__row">
                    <span className="list-item__title">{reminder.title}</span>
                    <span className="pill">{REPEAT_TYPE_LABEL[reminder.repeat_type]}</span>
                    <span
                      className={`pill pill--${
                        reminder.status === REMINDER_STATUS.COMPLETED ? 'green' : 'gray'
                      }`}
                    >
                      {REMINDER_STATUS_LABEL[reminder.status]}
                    </span>
                  </div>
                  <div className="list-item__sub">
                    下次提醒：{formatFullDateTime(reminder.next_trigger_at, timezone)}
                  </div>
                  <div className="btn-row">
                    <button
                      className="btn btn--secondary btn--small"
                      type="button"
                      onClick={() => setEditingId(reminder.id)}
                    >
                      <Pencil aria-hidden="true" />
                      修改
                    </button>
                    <button
                      className="btn btn--danger btn--small"
                      type="button"
                      onClick={() => handleDelete(reminder.id, reminder.title)}
                    >
                      <Trash2 aria-hidden="true" />
                      删除
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
