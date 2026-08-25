import test from 'node:test'
import assert from 'node:assert/strict'

import {
  MAX_CHAT_HISTORY,
  archiveConversation,
  clearChatHistory,
  loadChatHistory,
  saveChatHistory,
} from './chatStorage.js'


function installStorage() {
  const values = new Map()
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  }
  return values
}

test('archives the current conversation without losing earlier messages', () => {
  installStorage()
  const archived = archiveConversation(
    [{ id: 'old', text: '旧消息' }],
    [{ id: 'current', text: '当前消息' }],
  )
  saveChatHistory('user-1', {
    messages: [{ id: 'new', text: '新会话' }],
    archivedMessages: archived,
    conversationId: 'conversation-2',
  })

  assert.deepEqual(loadChatHistory('user-1'), {
    messages: [{ id: 'new', text: '新会话' }],
    archivedMessages: [
      { id: 'old', text: '旧消息' },
      { id: 'current', text: '当前消息' },
    ],
    conversationId: 'conversation-2',
  })
})

test('account cleanup removes current and legacy chat storage', () => {
  const values = installStorage()
  values.set('yoko.chat.v2.user-1', 'current')
  values.set('yoko.chat.user-1', 'legacy')

  clearChatHistory('user-1')

  assert.equal(values.size, 0)
})

test('current messages take priority when the history limit is reached', () => {
  installStorage()
  const current = Array.from({ length: MAX_CHAT_HISTORY }, (_, index) => ({
    id: `current-${index}`,
  }))

  saveChatHistory('user-1', {
    messages: current,
    archivedMessages: [{ id: 'archived' }],
    conversationId: 'conversation-full',
  })

  const loaded = loadChatHistory('user-1')
  assert.equal(loaded.messages.length, MAX_CHAT_HISTORY)
  assert.deepEqual(loaded.archivedMessages, [])
})
