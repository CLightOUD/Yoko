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

// Asia/Shanghai 固定 UTC+8，无夏令时，可安全地做手动时区换算。
// MVP 演示用户时区固定为 Asia/Shanghai（见 API_SPEC 3.5）。
const SHANGHAI_OFFSET_MS = 8 * 60 * 60 * 1000

function toShanghaiParts(iso) {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  const shifted = new Date(date.getTime() + SHANGHAI_OFFSET_MS)
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
    weekday: shifted.getUTCDay(),
  }
}

function pad(value) {
  return String(value).padStart(2, '0')
}

// “2026年8月22日 星期六 19:00”——用于需要公历日期、星期与钟点的场景（适老化核对）。
export function formatFullDateTime(iso) {
  const p = toShanghaiParts(iso)
  if (!p) return '—'
  return `${p.year}年${p.month}月${p.day}日 ${WEEKDAYS[p.weekday]} ${pad(p.hour)}:${pad(p.minute)}`
}

// “8月22日 星期六 19:00”——用于列表等紧凑场景。
export function formatDateTime(iso) {
  const p = toShanghaiParts(iso)
  if (!p) return '—'
  return `${p.month}月${p.day}日 ${WEEKDAYS[p.weekday]} ${pad(p.hour)}:${pad(p.minute)}`
}

// “19:00”——仅显示钟点。
export function formatTime(iso) {
  const p = toShanghaiParts(iso)
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
// MVP 演示固定 Asia/Shanghai（UTC+8）。
export function localToIso(localDateTime) {
  if (!localDateTime) return ''
  return `${localDateTime}:00+08:00`
}

// 把带时区 ISO 转回 <input type="datetime-local"> 的本地输入值（注意：datetime-local 本身无时区，
// 与 localToIso 的 +08:00 对称，仅用于回填编辑表单展示，避免时区偏移）。
export function isoToLocalInput(iso) {
  const p = toShanghaiParts(iso)
  if (!p) return ''
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`
}

export { DEFAULT_TIMEZONE }