import { DEFAULT_TIMEZONE } from './constants'

const WEEKDAYS = [
  '星期日',
  '星期一',
  '星期二',
  '星期三',
  '星期四',
  '星期五',
  '星期六',
]

// 使用 Intl.DateTimeFormat 将 ISO 时间字符串按指定时区拆解为各部分
// 相比手动加减偏移，这种方式天然支持夏令时和任意 IANA 时区
function toZonedParts(iso, timezone = DEFAULT_TIMEZONE) {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null

  try {
    const fmt = new Intl.DateTimeFormat('zh-CN', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      weekday: 'short',
      hour12: false,
    })
    const parts = fmt.formatToParts(date)
    const get = (type) => parts.find((p) => p.type === type)?.value ?? ''

    const weekdayMap = {
      '周日': 0, '周一': 1, '周二': 2, '周三': 3,
      '周四': 4, '周五': 5, '周六': 6,
    }
    const weekdayStr = get('weekday')
    const weekday = weekdayMap[weekdayStr] ?? 0

    return {
      year: parseInt(get('year'), 10),
      month: parseInt(get('month'), 10),
      day: parseInt(get('day'), 10),
      hour: parseInt(get('hour'), 10),
      minute: parseInt(get('minute'), 10),
      weekday,
    }
  } catch {
    // 时区无效时回退到本地时区
    return {
      year: date.getFullYear(),
      month: date.getMonth() + 1,
      day: date.getDate(),
      hour: date.getHours(),
      minute: date.getMinutes(),
      weekday: date.getDay(),
    }
  }
}

function pad(value) {
  return String(value).padStart(2, '0')
}

// “2026年8月22日 星期六 19:00”——用于需要公历日期、星期与钟点的场景（适老化核对）。
export function formatFullDateTime(iso, timezone) {
  const p = toZonedParts(iso, timezone)
  if (!p) return '—'
  return `${p.year}年${p.month}月${p.day}日 ${WEEKDAYS[p.weekday]} ${pad(p.hour)}:${pad(p.minute)}`
}

// “8月22日 星期六 19:00”——用于列表等紧凑场景。
export function formatDateTime(iso, timezone) {
  const p = toZonedParts(iso, timezone)
  if (!p) return '—'
  return `${p.month}月${p.day}日 ${WEEKDAYS[p.weekday]} ${pad(p.hour)}:${pad(p.minute)}`
}

// “19:00”——仅显示钟点。
export function formatTime(iso, timezone) {
  const p = toZonedParts(iso, timezone)
  if (!p) return '—'
  return `${pad(p.hour)}:${pad(p.minute)}`
}

// 把毫秒时长格式化为易读文本，用于指标展示。
export function formatMs(ms) {
  if (ms == null || Number.isNaN(ms)) return '—'
  if (ms < 1000) return `${Math.round(ms)} 毫秒`
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} 秒`
}

// 把 <input type="datetime-local"> 的值（如 "2026-08-22T19:00"）转为后端要求的带时区 ISO 字符串。
// 使用 Intl.DateTimeFormat 反推本地日期在指定时区下的 UTC 偏移，避免硬编码 +08:00。
export function localToIso(localDateTime, timezone = DEFAULT_TIMEZONE) {
  if (!localDateTime) return ''
  // 先解析为本地时间的 Date（datetime-local 无时区，按本地时区解释）
  const localDate = new Date(`${localDateTime}:00`)
  if (Number.isNaN(localDate.getTime())) return ''

  try {
    // 找到该日期在目标时区下的 UTC 偏移
    const fmt = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
    const parts = fmt.formatToParts(localDate)
    const get = (type) => parts.find((p) => p.type === type)?.value ?? '0'

    const zonedYear = parseInt(get('year'), 10)
    const zonedMonth = parseInt(get('month'), 10)
    const zonedDay = parseInt(get('day'), 10)
    const zonedHour = parseInt(get('hour'), 10)
    const zonedMinute = parseInt(get('minute'), 10)

    // 构造目标时区下的"名义时间"对应的 UTC 时间
    // 方法：用 UTC 时间构造，然后比较目标时区格式化结果与期望的差异
    let utcDate = new Date(Date.UTC(zonedYear, zonedMonth - 1, zonedDay, zonedHour, zonedMinute, 0))

    // 迭代校准：用当前猜测的 UTC 时间再格式化一次，如果与时区时间有偏差则调整
    for (let i = 0; i < 3; i++) {
      const checkParts = fmt.formatToParts(utcDate)
      const getC = (type) => checkParts.find((p) => p.type === type)?.value ?? '0'
      const h = parseInt(getC('hour'), 10)
      const m = parseInt(getC('minute'), 10)
      const diffMin = (zonedHour - h) * 60 + (zonedMinute - m)
      if (Math.abs(diffMin) < 1) break
      utcDate = new Date(utcDate.getTime() + diffMin * 60 * 1000)
    }

    // 计算与 UTC 的偏移（分钟）
    const offsetMs = localDate.getTime() - utcDate.getTime()
    const offsetMin = Math.round(offsetMs / 60000)
    const sign = offsetMin >= 0 ? '+' : '-'
    const absMin = Math.abs(offsetMin)
    const offsetHours = Math.floor(absMin / 60)
    const offsetMins = absMin % 60
    const offsetStr = `${sign}${pad(offsetHours)}:${pad(offsetMins)}`

    // 返回带偏移的 ISO 字符串：YYYY-MM-DDTHH:mm:ss+HH:mm
    const year = zonedYear
    const month = pad(zonedMonth)
    const day = pad(zonedDay)
    const hour = pad(zonedHour)
    const minute = pad(zonedMinute)
    return `${year}-${month}-${day}T${hour}:${minute}:00${offsetStr}`
  } catch {
    // 回退：简单拼接 +08:00（兼容旧行为）
    return `${localDateTime}:00+08:00`
  }
}

// 把带时区 ISO 转回 <input type="datetime-local"> 的本地输入值
export function isoToLocalInput(iso, timezone) {
  const p = toZonedParts(iso, timezone)
  if (!p) return ''
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`
}

export { DEFAULT_TIMEZONE }
