import { useState } from 'react'
import { Eye, EyeOff, KeyRound, LogIn, UserPlus } from 'lucide-react'
import { useAuth } from '../auth/useAuth'
import { DEFAULT_TIMEZONE } from '../api/constants'

const USERNAME_PATTERN = /^[A-Za-z0-9_]+$/

export default function AuthPage() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState('login') // 'login' | 'register'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const isRegister = mode === 'register'

  function switchMode(next) {
    if (next === mode) return
    setMode(next)
    setError('')
  }

  function validate() {
    const name = username.trim()
    if (name.length < 3 || name.length > 32 || !USERNAME_PATTERN.test(name)) {
      return '用户名需为 3~32 位，仅支持字母、数字和下划线'
    }
    if (password.length < 8 || password.length > 128) {
      return '密码长度需为 8~128 个字符'
    }
    if (isRegister) {
      const display = displayName.trim()
      if (display.length < 1 || display.length > 32) {
        return '显示名需为 1~32 个字符'
      }
      if (password !== confirmPassword) {
        return '两次输入的密码不一致'
      }
    }
    return ''
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (loading) return

    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }

    setError('')
    setLoading(true)
    try {
      if (isRegister) {
        await register({
          username: username.trim(),
          password,
          display_name: displayName.trim(),
          timezone: DEFAULT_TIMEZONE,
        })
      } else {
        await login({ username: username.trim(), password })
      }
      // 成功后由 App 依据认证状态切换到主界面
    } catch (err) {
      setError(err.message || '操作失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const toggleButton = (
    <button
      type="button"
      className="auth-pass-toggle"
      onClick={() => setShowPassword((prev) => !prev)}
      aria-label={showPassword ? '隐藏密码' : '显示密码'}
    >
      {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
    </button>
  )

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <img className="app-logo" src="/logo.svg" alt="渔歌" />
          <h1>Yoko 关怀助手</h1>
        </div>

        <h2 className="auth-title">{isRegister ? '注册账号' : '欢迎回来'}</h2>

        <form className="form-group" onSubmit={handleSubmit} noValidate>
          {isRegister && (
            <div className="form-row">
              <label htmlFor="auth-display-name">显示名</label>
              <input
                id="auth-display-name"
                className="field"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="例如：李阿姨"
                maxLength={32}
                autoComplete="name"
                autoFocus
              />
            </div>
          )}

          <div className="form-row">
            <label htmlFor="auth-username">用户名</label>
            <input
              id="auth-username"
              className="field"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="仅支持字母、数字和下划线"
              maxLength={32}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck="false"
              autoFocus={!isRegister}
            />
          </div>

          <div className="form-row">
            <label htmlFor="auth-password">密码</label>
            <div className="auth-pass">
              <input
                id="auth-password"
                className="field"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="至少 8 位"
                maxLength={128}
                autoComplete={isRegister ? 'new-password' : 'current-password'}
              />
              {toggleButton}
            </div>
          </div>

          {isRegister && (
            <div className="form-row">
              <label htmlFor="auth-confirm-password">确认密码</label>
              <div className="auth-pass">
                <input
                  id="auth-confirm-password"
                  className="field"
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="再次输入密码"
                  maxLength={128}
                  autoComplete="new-password"
                />
                {toggleButton}
              </div>
            </div>
          )}

          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}

          <button className="btn auth-submit" type="submit" disabled={loading}>
            {isRegister ? <UserPlus aria-hidden="true" /> : <LogIn aria-hidden="true" />}
            {loading
              ? isRegister
                ? '注册中…'
                : '登录中…'
              : isRegister
                ? '注册并登录'
                : '登录'}
          </button>
        </form>

        <div className="auth-switch">
          {isRegister ? (
            <>
              已有账号？
              <button type="button" onClick={() => switchMode('login')}>
                去登录
              </button>
            </>
          ) : (
            <>
              还没有账号？
              <button type="button" onClick={() => switchMode('register')}>
                <KeyRound aria-hidden="true" />
                注册新账号
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
