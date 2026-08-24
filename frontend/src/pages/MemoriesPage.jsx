import { useCallback, useEffect, useState } from 'react'
import { Pause, RefreshCw, Trash2 } from 'lucide-react'
import { deleteMemory, listMemories, updateMemory } from '../api/client'
import { MEMORY_SCOPE, TASK_TYPE_LABEL } from '../api/constants'
import { formatDateTime } from '../api/format'

export default function MemoriesPage() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await listMemories({ active: true })
      setItems(res.items)
      setTotal(res.total)
    } catch (err) {
      setError(err.message || '加载记忆失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleDisable(id) {
    try {
      await updateMemory(id, { active: false })
      load()
    } catch (err) {
      setError(err.message || '操作失败，请重试')
    }
  }

  async function handleDelete(id, displayText) {
    const confirmed = window.confirm(`确定要删除“${displayText}”这条记忆吗？`)
    if (!confirmed) return
    try {
      await deleteMemory(id)
      load()
    } catch (err) {
      setError(err.message || '删除失败，请重试')
    }
  }

  return (
    <div className="page">
      <div className="page-actions">
        <h1 className="page-title">记忆</h1>
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

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="empty">正在加载…</p>
      ) : items.length === 0 ? (
        <p className="empty">您还没有记忆。在对话中表达长期偏好，Yoko 会帮您记住。</p>
      ) : (
        <div className="card">
          <h2 className="section-title">已记住（{total}）</h2>
          {items.map((memory) => (
            <div key={memory.id} className="list-item">
              <div className="list-item__row">
                <span className="list-item__title">{memory.display_text}</span>
                <span className="pill">
                  {TASK_TYPE_LABEL[memory.task_type] ?? memory.task_type}
                </span>
                {memory.scope === MEMORY_SCOPE.GLOBAL && (
                  <span className="pill pill--green">全局偏好</span>
                )}
              </div>
              {memory.memory_value && (
                <div className="list-item__sub">内容：{memory.memory_value}</div>
              )}
              <div className="list-item__sub">
                最近使用：
                {memory.last_used_at ? formatDateTime(memory.last_used_at) : '尚未使用'}
              </div>
              <div className="list-item__row">
                <button
                  className="btn btn--secondary btn--small"
                  type="button"
                  onClick={() => handleDisable(memory.id)}
                >
                  <Pause aria-hidden="true" />
                  停用
                </button>
                <button
                  className="btn btn--danger btn--small"
                  type="button"
                  onClick={() => handleDelete(memory.id, memory.display_text)}
                >
                  <Trash2 aria-hidden="true" />
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}