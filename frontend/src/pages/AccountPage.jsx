import { useState } from 'react'
import { Download, Eye, EyeOff, KeyRound, ShieldCheck, Trash2, User } from 'lucide-react'
import { useAuth } from '../auth/useAuth'
import { ERROR_CODE } from '../api/constants'

function PasswordField({ id, label, value, onChange, placeholder, autoComplete, autoFocus }) {
  const [show, setShow] = useState(false)
  return (
    <div className="form-row">
      <label htmlFor={id}>{label}</label>
      <div className="auth-pass">
        <input
          id={id}
          className="field"
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          maxLength={128}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
        />
        <button
          type="button"
          className="auth-pass-toggle"
          onClick={() => setShow((prev) => !prev)}
          aria-label={show ? '隐藏密码' : '显示密码'}
        >
          {show ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
        </button>
      </div>
    </div>
  )
}

function ChangePasswordSection() {
  const { updatePassword } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (loading) return
    setError('')
    setSuccess('')

    if (current.length < 8) {
      setError('当前密码长度需为 8~128 个字符')
      return
    }
    if (next.length < 8 || next.length > 128) {
      setError('新密码长度需为 8~128 个字符')
      return
    }
    if (next === current) {
      setError('新密码不能与当前密码相同')
      return
    }
    if (next !== confirm) {
      setError('两次输入的新密码不一致')
      return
    }

    setLoading(true)
    try {
      await updatePassword({ current_password: current, new_password: next })
      setCurrent('')
      setNext('')
      setConfirm('')
      setSuccess('密码已修改，所有其他设备已自动退出登录。')
    } catch (err) {
      if (err?.code === ERROR_CODE.INVALID_CREDENTIALS) {
        setError('当前密码不正确')
      } else if (err?.code === ERROR_CODE.INVALID_REQUEST) {
        setError(err.message || '请求无效，请检查后重试')
      } else {
        setError(err?.message || '修改失败，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">
        <KeyRound aria-hidden="true" />
        修改密码
      </h2>
      <form className="form-group" onSubmit={handleSubmit} noValidate>
        <PasswordField
          id="account-current-password"
          label="当前密码"
          value={current}
          onChange={setCurrent}
          placeholder="请输入当前密码"
          autoComplete="current-password"
          autoFocus
        />
        <PasswordField
          id="account-new-password"
          label="新密码"
          value={next}
          onChange={setNext}
          placeholder="至少 8 位"
          autoComplete="new-password"
        />
        <PasswordField
          id="account-confirm-password"
          label="确认新密码"
          value={confirm}
          onChange={setConfirm}
          placeholder="再次输入新密码"
          autoComplete="new-password"
        />
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        {success && (
          <div className="success-banner" role="status">
            {success}
          </div>
        )}
        <button className="btn" type="submit" disabled={loading}>
          <ShieldCheck aria-hidden="true" />
          {loading ? '修改中…' : '修改密码'}
        </button>
      </form>
    </div>
  )
}

function ExportSection() {
  const { exportData } = useAuth()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleExport() {
    if (loading) return
    setError('')
    setLoading(true)
    try {
      await exportData()
    } catch (err) {
      setError(err?.message || '导出失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">
        <Download aria-hidden="true" />
        导出我的数据
      </h2>
      <p className="section-desc">
        导出您的账号资料、消息、提醒、记忆、反馈和指标，保存为 JSON 文件。
        不包含密码和 Session 信息。
      </p>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <button className="btn btn--secondary" type="button" onClick={handleExport} disabled={loading}>
        <Download aria-hidden="true" />
        {loading ? '正在生成…' : '下载个人数据'}
      </button>
    </div>
  )
}

function DeleteAccountSection() {
  const { removeAccount } = useAuth()
  const [step, setStep] = useState(1) // 1: 初始  2: 密码确认  3: 二次确认
  const [password, setPassword] = useState('')
  const [confirmText, setConfirmText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function reset() {
    setStep(1)
    setPassword('')
    setConfirmText('')
    setError('')
  }

  function goToPasswordConfirm() {
    setError('')
    setStep(2)
  }

  function handlePasswordSubmit(e) {
    e.preventDefault()
    if (password.length < 8) {
      setError('密码长度需为 8~128 个字符')
      return
    }
    setError('')
    setStep(3)
  }

  async function handleFinalConfirm() {
    if (loading) return
    if (confirmText.trim() !== '确认注销') {
      setError('请输入“确认注销”以继续')
      return
    }
    setLoading(true)
    setError('')
    try {
      await removeAccount({ password })
      // 成功后由 AuthContext 切换到未登录状态
    } catch (err) {
      if (err?.code === ERROR_CODE.INVALID_CREDENTIALS) {
        setError('密码不正确，注销未执行')
        setStep(2)
      } else {
        setError(err?.message || '注销失败，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card card--danger">
      <h2 className="section-title section-title--danger">
        <Trash2 aria-hidden="true" />
        注销账户
      </h2>
      <p className="section-desc">
        注销后您的所有数据（消息、提醒、记忆、反馈、指标）将被永久删除，且无法恢复。
        此操作不可撤销。
      </p>

      {step === 1 && (
        <>
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          <button
            className="btn btn--danger"
            type="button"
            onClick={goToPasswordConfirm}
          >
            <Trash2 aria-hidden="true" />
            开始注销流程
          </button>
        </>
      )}

      {step === 2 && (
        <form className="form-group" onSubmit={handlePasswordSubmit} noValidate>
          <PasswordField
            id="delete-account-password"
            label="请输入当前密码以确认身份"
            value={password}
            onChange={setPassword}
            placeholder="当前登录密码"
            autoComplete="current-password"
            autoFocus
          />
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          <div className="btn-row">
            <button className="btn btn--secondary" type="button" onClick={reset}>
              取消
            </button>
            <button className="btn btn--danger" type="submit">
              继续
            </button>
          </div>
        </form>
      )}

      {step === 3 && (
        <div className="form-group">
          <div className="danger-warning" role="alert">
            <strong>最后确认：</strong>注销账户将永久删除您的全部数据，
            包括所有聊天记录、提醒、记忆、反馈和指标。此操作无法撤销。
          </div>
          <div className="form-row">
            <label htmlFor="delete-confirm-text">
              请输入“确认注销”以继续
            </label>
            <input
              id="delete-confirm-text"
              className="field"
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="确认注销"
              autoComplete="off"
              autoFocus
            />
          </div>
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          <div className="btn-row">
            <button className="btn btn--secondary" type="button" onClick={reset} disabled={loading}>
              取消
            </button>
            <button
              className="btn btn--danger"
              type="button"
              onClick={handleFinalConfirm}
              disabled={loading || confirmText.trim() !== '确认注销'}
            >
              {loading ? '注销中…' : '永久注销账户'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function AccountPage() {
  const { user, sessionExpiresAt } = useAuth()

  const formatExpire = (iso) => {
    if (!iso) return '—'
    try {
      return new Date(iso).toLocaleString('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  return (
    <div className="page">
      <div className="page-actions">
        <h1 className="page-title">账户</h1>
      </div>

      <div className="card">
        <div className="account-info">
          <div className="account-info__avatar">
            <User aria-hidden="true" />
          </div>
          <div className="account-info__detail">
            <div className="account-info__name">
              {user?.display_name || user?.username || '—'}
            </div>
            <div className="account-info__sub">
              用户名：{user?.username || '—'}
            </div>
            <div className="account-info__sub">
              时区：{user?.timezone || 'Asia/Shanghai'}
            </div>
            {sessionExpiresAt && (
              <div className="account-info__sub">
                登录有效期至：{formatExpire(sessionExpiresAt)}
              </div>
            )}
          </div>
        </div>
      </div>

      <ChangePasswordSection />
      <ExportSection />
      <DeleteAccountSection />
    </div>
  )
}
