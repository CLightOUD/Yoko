// 前端固定使用的 MVP 用户与默认时区（见 API_SPEC 3.5）
export const USER_ID = 'demo-user'
export const DEFAULT_TIMEZONE = 'Asia/Shanghai'

// 记忆范围 scope
export const MEMORY_SCOPE = {
  GLOBAL: 'global',
  TASK: 'task',
}

// 任务分类 task_type
export const TASK_TYPE = {
  GLOBAL: 'global',
  MEDICATION: 'medication',
  WALKING: 'walking',
  APPOINTMENT: 'appointment',
  OTHER: 'other',
}

// 记忆变更动作 action
export const MEMORY_ACTION = {
  CREATED: 'created',
  UPDATED: 'updated',
  SKIPPED: 'skipped',
}

// Agent 对话状态
export const CHAT_STATUS = {
  COMPLETED: 'completed',
  NEEDS_CLARIFICATION: 'needs_clarification',
  PARTIAL: 'partial',
}

// 工具调用状态
export const TOOL_STATUS = {
  SUCCESS: 'success',
  FAILED: 'failed',
}

// 提醒重复周期
export const REPEAT_TYPE = {
  NONE: 'none',
  DAILY: 'daily',
  WEEKLY: 'weekly',
}

// 提醒状态
export const REMINDER_STATUS = {
  ACTIVE: 'active',
  COMPLETED: 'completed',
  DELETED: 'deleted',
}

// 查询提醒时可选的状态（含“全部”专用值）
export const REMINDER_LIST_STATUS = {
  ...REMINDER_STATUS,
  ALL: 'all',
}

// 反馈评分
export const FEEDBACK_RATING = {
  UP: 'up',
  DOWN: 'down',
}

// 稳定错误码（见 API_SPEC 3.4）
export const ERROR_CODE = {
  INVALID_REQUEST: 'INVALID_REQUEST',
  RESOURCE_NOT_FOUND: 'RESOURCE_NOT_FOUND',
  RESOURCE_CONFLICT: 'RESOURCE_CONFLICT',
  MODEL_UNAVAILABLE: 'MODEL_UNAVAILABLE',
  TOOL_EXECUTION_FAILED: 'TOOL_EXECUTION_FAILED',
  INTERNAL_ERROR: 'INTERNAL_ERROR',
}

// 面向用户的中文显示标签
export const TASK_TYPE_LABEL = {
  [TASK_TYPE.GLOBAL]: '通用',
  [TASK_TYPE.MEDICATION]: '服药',
  [TASK_TYPE.WALKING]: '散步',
  [TASK_TYPE.APPOINTMENT]: '预约',
  [TASK_TYPE.OTHER]: '其他',
}

export const REPEAT_TYPE_LABEL = {
  [REPEAT_TYPE.NONE]: '一次性',
  [REPEAT_TYPE.DAILY]: '每天',
  [REPEAT_TYPE.WEEKLY]: '每周',
}

export const REMINDER_STATUS_LABEL = {
  [REMINDER_STATUS.ACTIVE]: '进行中',
  [REMINDER_STATUS.COMPLETED]: '已完成',
  [REMINDER_STATUS.DELETED]: '已删除',
}

export const MEMORY_ACTION_LABEL = {
  [MEMORY_ACTION.CREATED]: '新增',
  [MEMORY_ACTION.UPDATED]: '更新',
  [MEMORY_ACTION.SKIPPED]: '跳过',
}