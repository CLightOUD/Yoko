import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import { acknowledgeReminder, listDueReminders } from './api/client'
import { REPEAT_TYPE_LABEL } from './api/constants'
import { formatFullDateTime } from './api/format'
import { playAlarm, unlockAudio } from './alarm'

// 到期提醒轮询周期（规范建议 20–30 秒）
const POLL_MS = 25000

const keyOf = (r) => `${r.id}:${r.next_trigger_at}`

// 浏览器通知权限管理：未授权时在首次交互后请求
async function ensureNotificationPermission() {
  if (typeof Notification === 'undefined') return 'unsupported'
  if (Notification.permission === 'granted') return 'granted'
  if (Notification.permission === 'denied') return 'denied'
  try {
    const result = await Notification.requestPermission()
    return result
  } catch {
    return 'default'
  }
}

function showNotification(reminder) {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
  try {
    const n = new Notification('⏰ 提醒时间到', {
      body: reminder.title,
      tag: `reminder-${reminder.id}`,
      renotify: true,
    })
    n.onclick = () => {
      window.focus()
      n.close()
    }
  } catch {
    // 通知不可用时静默降级为纯弹窗
  }
}

// 全站常驻：轮询到期提醒，弹窗 + 提示音 + 浏览器通知 + 确认（/reminders/due + /reminders/{id}/ack）
export default function ReminderAlarm() {
  const [alarm, setAlarm] = useState(null)
  const [queue, setQueue] = useState([])
  const [acknowledging, setAcknowledging] = useState(false)
  const [ackError, setAckError] = useState('')
  const seenRef = useRef(new Set())
  const notifiedRef = useRef(new Set())

  const poll = useCallback(async () => {
    try {
      const res = await listDueReminders({ limit: 20 })
      const items = res.items ?? []
      // 同一提醒确认前可能被多次轮询到，按 id + next_trigger_at 去重
      const fresh = items.filter((r) => !seenRef.current.has(keyOf(r)))
      if (fresh.length > 0) {
        setQueue((prev) => {
          const existing = new Set(prev.map(keyOf))
          return [...prev, ...fresh.filter((r) => !existing.has(keyOf(r)))]
        })
      }
      // 浏览器通知：每条到期提醒只推送一次
      items.forEach((r) => {
        const k = keyOf(r)
        if (!notifiedRef.current.has(k)) {
          notifiedRef.current.add(k)
          showNotification(r)
        }
      })
    } catch {
      // 轮询失败静默，下一轮自动重试
    }
  }, [])

  useEffect(() => {
    const unlock = () => {
      unlockAudio()
      // 首次交互时顺便请求通知权限（浏览器要求必须在用户手势内）
      ensureNotificationPermission()
    }
    window.addEventListener('pointerdown', unlock, { once: true })
    window.addEventListener('keydown', unlock, { once: true })

    poll()
    const timer = setInterval(poll, POLL_MS)

    // 页面重新可见时立即补查，避免标签页后台期间漏查
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        poll()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)

    const onFocus = () => poll()
    window.addEventListener('focus', onFocus)

    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
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
