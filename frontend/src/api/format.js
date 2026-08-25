import { DEFAULT_TIMEZONE } from './constants.js'

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
      hourCycle: 'h23',
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

// 把 datetime-local 的墙上时间按指定 IANA 时区转换为 UTC ISO 字符串。
export function localToIso(localDateTime, timezone = DEFAULT_TIMEZONE) {
  if (!localDateTime) return ''
  const match = localDateTime.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/,
  )
  if (!match) return ''

  const desired = {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
    second: Number(match[6] ?? 0),
  }
  const desiredUtc = Date.UTC(
    desired.year,
    desired.month - 1,
    desired.day,
    desired.hour,
    desired.minute,
    desired.second,
  )
  const normalized = new Date(desiredUtc)
  if (
    normalized.getUTCFullYear() !== desired.year ||
    normalized.getUTCMonth() + 1 !== desired.month ||
    normalized.getUTCDate() !== desired.day ||
    normalized.getUTCHours() !== desired.hour ||
    normalized.getUTCMinutes() !== desired.minute ||
    normalized.getUTCSeconds() !== desired.second
  ) {
    return ''
  }

  try {
    const fmt = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    })
    const partsAt = (timestamp) => {
      const parts = fmt.formatToParts(new Date(timestamp))
      const get = (type) => Number(parts.find((part) => part.type === type)?.value)
      return {
        year: get('year'),
        month: get('month'),
        day: get('day'),
        hour: get('hour'),
        minute: get('minute'),
        second: get('second'),
      }
    }

    let candidate = desiredUtc
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const rendered = partsAt(candidate)
      const renderedAsUtc = Date.UTC(
        rendered.year,
        rendered.month - 1,
        rendered.day,
        rendered.hour,
        rendered.minute,
        rendered.second,
      )
      const adjustment = desiredUtc - renderedAsUtc
      if (adjustment === 0) break
      candidate += adjustment
    }

    const verified = partsAt(candidate)
    if (Object.keys(desired).some((key) => verified[key] !== desired[key])) {
      return ''
    }
    return new Date(candidate).toISOString()
  } catch {
    return ''
  }
}

// 把带时区 ISO 转回 <input type="datetime-local"> 的本地输入值
export function isoToLocalInput(iso, timezone) {
  const p = toZonedParts(iso, timezone)
  if (!p) return ''
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`
}

export { DEFAULT_TIMEZONE }
