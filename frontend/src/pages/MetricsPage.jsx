import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { getMetricsSummary } from '../api/client'
import { formatDateTime, formatMs } from '../api/format'

function ratio(numerator, denominator) {
  if (!denominator) return '0%'
  return `${((numerator / denominator) * 100).toFixed(0)}%`
}

function Metric({ label, value, note }) {
  return (
    <div className="metric">
      <div className="metric__value">{value}</div>
      <div className="metric__label">
        {label}
        {note ? `（${note}）` : ''}
      </div>
    </div>
  )
}

export default function MetricsPage() {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await getMetricsSummary()
      setSummary(res)
    } catch (err) {
      setError(err.message || '加载指标失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="page">
      <div className="page-actions">
        <h1 className="page-title">指标</h1>
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
      ) : summary ? (
        <>
          <div className="metric-grid">
            <Metric label="请求次数" value={summary.request_count} />
            <Metric label="模型调用次数" value={summary.model_call_count} />
            <Metric
              label="输入 Token"
              value={summary.input_tokens}
              note={summary.token_metrics_complete ? undefined : '不完整'}
            />
            <Metric label="输出 Token" value={summary.output_tokens} />
            <Metric label="记忆 Token" value={summary.memory_tokens} />
            <Metric
              label="记忆检索命中率"
              value={ratio(
                summary.requests_with_retrieved_memory,
                summary.request_count,
              )}
            />
            <Metric
              label="记忆实际使用率"
              value={ratio(
                summary.requests_with_used_memory,
                summary.request_count,
              )}
            />
            <Metric
              label="记忆 Token 占比"
              value={ratio(summary.memory_tokens, summary.input_tokens)}
            />
            <Metric
              label="平均检索耗时"
              value={formatMs(summary.average_retrieval_ms)}
            />
            <Metric
              label="平均模型耗时"
              value={formatMs(summary.average_model_ms)}
            />
            <Metric
              label="平均总耗时"
              value={formatMs(summary.average_total_ms)}
            />
          </div>

          <p className="empty" style={{ fontSize: 'var(--font-size-sm)' }}>
            统计范围：
            {summary.from
              ? `${formatDateTime(summary.from)} 至 ${formatDateTime(summary.to)}`
              : `截至 ${formatDateTime(summary.to)}`}
          </p>
        </>
      ) : null}
    </div>
  )
}