import {
  DEFAULT_TIMEZONE,
  ERROR_CODE,
  REMINDER_STATUS,
  REPEAT_TYPE,
} from './constants'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

const REQUEST_TIMEOUT_MS = 30000

// 统一错误对象：把 ErrorResponse 转成可判定的异常（见 API_SPEC 3.4）。
export class ApiError extends Error {
  constructor({ code, message, details = null, requestId = null, status }) {
    super(message || `请求失败（HTTP ${status}）`)
    this.name = 'ApiError'
    this.code = code
    this.details = details
    this.requestId = requestId
    this.status = status
  }
}

function buildQuery(query) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value))
    }
  }
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

async function request(path, { method = 'GET', query, body } = {}) {
  const url = `${API_BASE_URL}${path}${buildQuery(query)}`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  let response
  try {
    response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
  } catch (error) {
    clearTimeout(timer)
    if (error.name === 'AbortError') {
      throw new ApiError({
        code: ERROR_CODE.INTERNAL_ERROR,
        message: '请求超时，请稍后重试',
        status: 0,
      })
    }
    throw new ApiError({
      code: ERROR_CODE.INTERNAL_ERROR,
      message: '无法连接服务器，请确认后端已启动',
      status: 0,
    })
  }
  clearTimeout(timer)

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    if (payload?.error) {
      throw new ApiError({
        code: payload.error.code,
        message: payload.error.message,
        details: payload.error.details,
        requestId: payload.request_id,
        status: response.status,
      })
    }
    throw new ApiError({
      code: ERROR_CODE.INTERNAL_ERROR,
      message: `请求失败（HTTP ${response.status}）`,
      status: response.status,
    })
  }

  return payload
}

// 健康检查
export function getHealth() {
  return request('/api/health')
}

// 对话：发送用户消息，返回 Agent 回复与记忆/工具/指标信息
export function sendChat({
  user_id,
  conversation_id = null,
  message,
  timezone = DEFAULT_TIMEZONE,
}) {
  return request('/api/chat', {
    method: 'POST',
    body: { user_id, conversation_id, message, timezone },
  })
}

// 结构化反馈：点赞/点踩/编辑
export function sendFeedback({
  user_id,
  request_id,
  feedback_text = null,
  corrected_reply = null,
  rating = null,
}) {
  return request('/api/feedback', {
    method: 'POST',
    body: { user_id, request_id, feedback_text, corrected_reply, rating },
  })
}

// 创建提醒
export function createReminder({
  user_id,
  title,
  next_trigger_at,
  timezone = DEFAULT_TIMEZONE,
  repeat_type = REPEAT_TYPE.NONE,
}) {
  return request('/api/reminders', {
    method: 'POST',
    body: { user_id, title, next_trigger_at, timezone, repeat_type },
  })
}

// 查询提醒列表
export function listReminders({
  user_id,
  status = REMINDER_STATUS.ACTIVE,
  limit = 50,
  offset = 0,
}) {
  return request('/api/reminders', {
    method: 'GET',
    query: { user_id, status, limit, offset },
  })
}

// 查询到期提醒
export function listDueReminders({ user_id, limit = 20 }) {
  return request('/api/reminders/due', {
    method: 'GET',
    query: { user_id, limit },
  })
}

// 修改提醒（只传入要修改的字段）
export function updateReminder(id, fields) {
  return request(`/api/reminders/${id}`, {
    method: 'PATCH',
    body: { ...fields, user_id: fields.user_id },
  })
}

// 删除提醒（软删除）
export function deleteReminder(id, user_id) {
  return request(`/api/reminders/${id}`, {
    method: 'DELETE',
    query: { user_id },
  })
}

// 确认提醒并推进周期
export function acknowledgeReminder(id, { user_id, expected_trigger_at }) {
  return request(`/api/reminders/${id}/ack`, {
    method: 'POST',
    body: { user_id, expected_trigger_at },
  })
}

// 查询记忆
export function listMemories({
  user_id,
  active = true,
  task_type = null,
  limit = 50,
  offset = 0,
}) {
  const query = { user_id, limit, offset }
  if (active !== null && active !== undefined) query.active = active
  if (task_type) query.task_type = task_type
  return request('/api/memories', { method: 'GET', query })
}

// 修改或停用记忆（只传入要修改的字段）
export function updateMemory(id, fields) {
  return request(`/api/memories/${id}`, {
    method: 'PATCH',
    body: { ...fields, user_id: fields.user_id },
  })
}

// 删除记忆（软删除）
export function deleteMemory(id, user_id) {
  return request(`/api/memories/${id}`, {
    method: 'DELETE',
    query: { user_id },
  })
}

// 查询指标汇总
export function getMetricsSummary({ user_id, from = null, to = null }) {
  const query = { user_id }
  if (from) query.from = from
  if (to) query.to = to
  return request('/api/metrics/summary', { method: 'GET', query })
}