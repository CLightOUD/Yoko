export const MAX_CHAT_HISTORY = 300

const STORAGE_VERSION = 2
const STORAGE_SIZE_LIMIT = 4.5 * 1024 * 1024


function storageKey(userId) {
  return `yoko.chat.v${STORAGE_VERSION}.${userId}`
}

function legacyStorageKey(userId) {
  return `yoko.chat.${userId}`
}

function trimMessages(messages, limit = MAX_CHAT_HISTORY) {
  if (limit <= 0) return []
  return messages.slice(-limit)
}

export function archiveConversation(archivedMessages, currentMessages) {
  return trimMessages([...(archivedMessages ?? []), ...(currentMessages ?? [])])
}

export function loadChatHistory(userId) {
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && Array.isArray(parsed.messages)) {
        const messages = trimMessages(parsed.messages)
        const archivedMessages = trimMessages(parsed.archivedMessages ?? [])
        return {
          messages,
          archivedMessages: trimMessages([
            ...archivedMessages,
          ], Math.max(0, MAX_CHAT_HISTORY - messages.length)),
          conversationId: parsed.conversationId ?? null,
        }
      }
    }
  } catch {
    // 存储损坏时尝试迁移旧版本。
  }

  try {
    const oldKey = legacyStorageKey(userId)
    const oldRaw = localStorage.getItem(oldKey)
    if (oldRaw) {
      const old = JSON.parse(oldRaw)
      if (old && Array.isArray(old.messages)) {
        const migrated = {
          messages: trimMessages(old.messages),
          archivedMessages: [],
          conversationId: old.conversationId ?? null,
        }
        saveChatHistory(userId, migrated)
        localStorage.removeItem(oldKey)
        return migrated
      }
    }
  } catch {
    // 迁移失败不阻断聊天。
  }

  return { messages: [], archivedMessages: [], conversationId: null }
}

export function saveChatHistory(
  userId,
  { messages, archivedMessages, conversationId },
) {
  const current = trimMessages(messages ?? [])
  let archived = trimMessages(
    archivedMessages ?? [],
    Math.max(0, MAX_CHAT_HISTORY - current.length),
  )
  try {
    let payload = JSON.stringify({
      messages: current,
      archivedMessages: archived,
      conversationId,
    })
    while (payload.length > STORAGE_SIZE_LIMIT && archived.length > 0) {
      archived = archived.slice(Math.max(1, Math.floor(archived.length / 2)))
      payload = JSON.stringify({
        messages: current,
        archivedMessages: archived,
        conversationId,
      })
    }
    localStorage.setItem(storageKey(userId), payload)
  } catch {
    // 存储已满或被禁用时不阻断聊天。
  }
}

export function clearChatHistory(userId) {
  try {
    localStorage.removeItem(storageKey(userId))
    localStorage.removeItem(legacyStorageKey(userId))
  } catch {
    // 浏览器禁用存储时无需额外处理。
  }
}
