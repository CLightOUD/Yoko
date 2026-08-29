import { useCallback, useEffect, useState } from 'react'
import { Pause, Play, RefreshCw, Trash2 } from 'lucide-react'
import { deleteMemory, listMemories, updateMemory } from '../api/client'
import { MEMORY_SCOPE, TASK_TYPE_LABEL } from '../api/constants'
import { formatDateTime } from '../api/format'

export default function MemoriesPage() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [activeFilter, setActiveFilter] = useState(true)
  const [pendingDeletion, setPendingDeletion] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await listMemories({ active: activeFilter })
      setItems(res.items)
      setTotal(res.total)
    } catch (err) {
      setError(err.message || '加载记忆失败')
    } finally {
      setLoading(false)
    }
  }, [activeFilter])

  useEffect(() => {
    let cancelled = false
    async function fetchData() {
      setLoading(true)
      setError('')
      try {
        const res = await listMemories({ active: activeFilter })
        if (!cancelled) {
          setItems(res.items)
          setTotal(res.total)
        }
      } catch (err) {
        if (!cancelled) setError(err.message || '加载记忆失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchData()
    return () => { cancelled = true }
  }, [activeFilter])

  async function handleDisable(id) {
    setBusyId(id)
    try {
      await updateMemory(id, { active: false })
      await load()
    } catch (err) {
      setError(err.message || '操作失败，请重试')
    } finally {
      setBusyId(null)
    }
  }

  async function handleEnable(id) {
    setBusyId(id)
    try {
      await updateMemory(id, { active: true })
      await load()
    } catch (err) {
      setError(err.message || '重新启用失败，请重试')
    } finally {
      setBusyId(null)
    }
  }

  async function confirmDelete() {
    if (!pendingDeletion || busyId) return
    setBusyId(pendingDeletion.id)
    try {
      await deleteMemory(pendingDeletion.id)
      setPendingDeletion(null)
      await load()
    } catch (err) {
      setError(err.message || '删除失败，请重试')
    } finally {
      setBusyId(null)
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

      <div className="filter-tabs" role="group" aria-label="按状态筛选记忆">
        <button
          type="button"
          className={`filter-tab${activeFilter ? ' filter-tab--active' : ''}`}
          onClick={() => setActiveFilter(true)}
        >
          使用中
        </button>
        <button
          type="button"
          className={`filter-tab${!activeFilter ? ' filter-tab--active' : ''}`}
          onClick={() => setActiveFilter(false)}
        >
          已停用
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
        <p className="empty">
          {activeFilter
            ? '您还没有使用中的记忆。在对话中表达长期偏好，Yoko 会帮您记住。'
            : '您没有已停用的记忆。'}
        </p>
      ) : (
        <div className="card">
          <h2 className="section-title">
            {activeFilter ? '使用中的记忆' : '已停用的记忆'}（{total}）
          </h2>
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
                {activeFilter ? (
                  <button
                    className="btn btn--secondary btn--small"
                    type="button"
                    onClick={() => handleDisable(memory.id)}
                    disabled={busyId === memory.id}
                  >
                    <Pause aria-hidden="true" />
                    停用
                  </button>
                ) : (
                  <button
                    className="btn btn--secondary btn--small"
                    type="button"
                    onClick={() => handleEnable(memory.id)}
                    disabled={busyId === memory.id}
                  >
                    <Play aria-hidden="true" />
                    重新启用
                  </button>
                )}
                <button
                  className="btn btn--danger btn--small"
                  type="button"
                  onClick={() => setPendingDeletion({
                    id: memory.id,
                    displayText: memory.display_text,
                  })}
                  disabled={busyId === memory.id}
                >
                  <Trash2 aria-hidden="true" />
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {pendingDeletion && (
        <div
          className="confirm-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !busyId) {
              setPendingDeletion(null)
            }
          }}
        >
          <div
            className="confirm-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-memory-title"
            aria-describedby="delete-memory-description"
          >
            <h2 id="delete-memory-title" className="section-title">永久删除记忆</h2>
            <p id="delete-memory-description">
              确定要永久删除“{pendingDeletion.displayText}”吗？删除后无法恢复。
            </p>
            <div className="btn-row confirm-dialog__actions">
              <button
                className="btn btn--secondary"
                type="button"
                onClick={() => setPendingDeletion(null)}
                disabled={Boolean(busyId)}
                autoFocus
              >
                取消
              </button>
              <button
                className="btn btn--danger"
                type="button"
                onClick={confirmDelete}
                disabled={Boolean(busyId)}
              >
                {busyId ? '正在删除…' : '永久删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
