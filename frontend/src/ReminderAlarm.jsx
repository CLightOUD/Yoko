import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import { acknowledgeReminder, listDueReminders } from './api/client'
import { REPEAT_TYPE_LABEL } from './api/constants'
import { formatFullDateTime } from './api/format'
import { playAlarm, unlockAudio } from './alarm'

// 到期提醒轮询周期（规范建议 20–30 秒）
const POLL_MS = 20000

const keyOf = (r) => `${r.id}:${r.next_trigger_at}`

// 全站常驻：轮询到期提醒，弹窗 + 提示音 + 确认（/reminders/due + /reminders/{id}/ack）
export default function ReminderAlarm() {
  const [alarm, setAlarm] = useState(null)
  const [queue, setQueue] = useState([])
  const [acknowledging, setAcknowledging] = useState(false)
  const [ackError, setAckError] = useState('')
  const seenRef = useRef(new Set())

  const poll = useCallback(async () => {
    try {
      const res = await listDueReminders({ limit: 20 })
      // 同一提醒确认前可能被多次轮询到，按 id + next_trigger_at 去重
      const fresh = (res.items ?? []).filter((r) => !seenRef.current.has(keyOf(r)))
      if (fresh.length === 0) return
      setQueue((prev) => {
        const existing = new Set(prev.map(keyOf))
        return [...prev, ...fresh.filter((r) => !existing.has(keyOf(r)))]
      })
    } catch {
      // 轮询失败静默，下一轮自动重试
    }
  }, [])

  useEffect(() => {
    const unlock = () => unlockAudio()
    window.addEventListener('pointerdown', unlock, { once: true })
    window.addEventListener('keydown', unlock, { once: true })
    poll()
    const timer = setInterval(poll, POLL_MS)
    const onFocus = () => poll()
    window.addEventListener('focus', onFocus)
    return () => {
      clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('pointerdown', unlock)
      window.removeEventListener('keydown', unlock)
    }
  }, [poll])

  // 有待确认项且当前无弹窗 → 弹出第一条并响铃
  useEffect(() => {
    if (queue.length && !alarm) {
      setAckError('')
      setAlarm(queue[0])
      playAlarm()
    }
  }, [queue, alarm])

  async function handleAck() {
    if (!alarm || acknowledging) return
    const target = alarm
    const key = keyOf(target)
    setAcknowledging(true)
    setAckError('')
    try {
      await acknowledgeReminder(target.id, {
        expected_trigger_at: target.next_trigger_at,
      })
      seenRef.current.add(key)
      setQueue((prev) => prev.filter((r) => keyOf(r) !== key))
      setAlarm(null)
    } catch (error) {
      setAckError(error.message || '确认失败，请检查网络后重试')
    } finally {
      setAcknowledging(false)
    }
  }

  if (!alarm) return null

  return (
    <div className="alarm-overlay" role="alertdialog" aria-modal="true" aria-label="到期提醒">
      <div className="alarm-card" role="document">
        <div className="alarm-head">
          <Bell aria-hidden="true" />
          <span>到时间啦</span>
        </div>
        <div className="alarm-title">{alarm.title}</div>
        <div className="alarm-meta">原定 {formatFullDateTime(alarm.next_trigger_at)}</div>
        {alarm.repeat_type && alarm.repeat_type !== 'none' && (
          <div className="alarm-meta">重复：{REPEAT_TYPE_LABEL[alarm.repeat_type]}</div>
        )}
        {queue.length > 1 && (
          <div className="alarm-meta">还有 {queue.length - 1} 条待确认</div>
        )}
        {ackError && (
          <div className="error-banner alarm-error" role="alert">
            {ackError}。这条提醒会继续保留，请再次确认。
          </div>
        )}
        <button
          className="alarm-ack"
          type="button"
          onClick={handleAck}
          disabled={acknowledging}
        >
          {acknowledging ? '确认中…' : ackError ? '重新确认' : '我知道了'}
        </button>
      </div>
    </div>
  )
}
