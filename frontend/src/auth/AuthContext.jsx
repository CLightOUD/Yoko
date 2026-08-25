import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  changePassword,
  deleteAccount,
  exportAccountData,
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from '../api/client'
import { AUTH_STATUS, ERROR_CODE } from '../api/constants'
import { AuthContext } from './useAuth'

const UNAUTHORIZED_EVENT = 'yoko:unauthorized'

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(AUTH_STATUS.LOADING)
  const [user, setUser] = useState(null)
  const [sessionExpiresAt, setSessionExpiresAt] = useState(null)
  const [error, setError] = useState('')

  const markUnauthenticated = useCallback(() => {
    setUser(null)
    setSessionExpiresAt(null)
    setError('')
    setStatus(AUTH_STATUS.UNAUTHENTICATED)
  }, [])

  const restoreSession = useCallback(async () => {
    setError('')
    setStatus(AUTH_STATUS.LOADING)
    try {
      const res = await getCurrentUser()
      setUser(res.user)
      setSessionExpiresAt(res.session_expires_at ?? null)
      setStatus(AUTH_STATUS.AUTHENTICATED)
    } catch (err) {
      if (
        err?.code === ERROR_CODE.AUTHENTICATION_REQUIRED ||
        err?.status === 401
      ) {
        markUnauthenticated()
        return
      }
      setUser(null)
      setSessionExpiresAt(null)
      setError(err?.message || '无法确认登录状态，请检查网络后重试')
      setStatus(AUTH_STATUS.ERROR)
    }
  }, [markUnauthenticated])

  // 启动/刷新时用 Cookie 调 /me 恢复登录状态
  useEffect(() => {
    let active = true
    getCurrentUser()
      .then((res) => {
        if (!active) return
        setUser(res.user)
        setSessionExpiresAt(res.session_expires_at ?? null)
        setStatus(AUTH_STATUS.AUTHENTICATED)
      })
      .catch((err) => {
        if (!active) return
        if (
          err?.code === ERROR_CODE.AUTHENTICATION_REQUIRED ||
          err?.status === 401
        ) {
          markUnauthenticated()
          return
        }
        setUser(null)
        setSessionExpiresAt(null)
        setError(err?.message || '无法确认登录状态，请检查网络后重试')
        setStatus(AUTH_STATUS.ERROR)
      })
    return () => {
      active = false
    }
  }, [markUnauthenticated])

  // 受保护接口返回 401 AUTHENTICATION_REQUIRED 时统一回到登录页
  useEffect(() => {
    window.addEventListener(UNAUTHORIZED_EVENT, markUnauthenticated)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, markUnauthenticated)
  }, [markUnauthenticated])

  const login = useCallback(async ({ username, password }) => {
    const res = await loginUser({ username, password })
    setUser(res.user)
    setSessionExpiresAt(res.session_expires_at ?? null)
    setStatus(AUTH_STATUS.AUTHENTICATED)
    return res
  }, [])

  const register = useCallback(
    async ({ username, password, display_name, timezone }) => {
      const res = await registerUser({
        username,
        password,
        display_name,
        timezone,
      })
      setUser(res.user)
      setSessionExpiresAt(res.session_expires_at ?? null)
      setStatus(AUTH_STATUS.AUTHENTICATED)
      return res
    },
    [],
  )

  const logout = useCallback(async () => {
    try {
      await logoutUser()
      markUnauthenticated()
    } catch (err) {
      // 服务器已判定会话失效时，本地也可以安全结束登录状态。
      if (
        err?.code === ERROR_CODE.AUTHENTICATION_REQUIRED ||
        err?.status === 401
      ) {
        markUnauthenticated()
        return
      }
      throw err
    }
  }, [markUnauthenticated])

  // 修改密码：成功后后端会签发新 Session，旧 Session 全部失效
  const updatePassword = useCallback(async ({ current_password, new_password }) => {
    const res = await changePassword({ current_password, new_password })
    setUser(res.user)
    setSessionExpiresAt(res.session_expires_at ?? null)
    return res
  }, [])

  // 导出账号数据：触发浏览器 JSON 文件下载
  const exportData = useCallback(async () => {
    const response = await exportAccountData()
    const blob = await response.blob()
    // 从 Content-Disposition 读取文件名，回退到默认名
    const disposition = response.headers.get('Content-Disposition')
    let filename = 'yoko-account-export.json'
    const match = disposition?.match(/filename="?([^";]+)"?/)
    if (match?.[1]) filename = match[1]

    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }, [])

  // 注销账户：需再次输入密码确认；成功后回到登录页
  const removeAccount = useCallback(async ({ password }) => {
    await deleteAccount({ password })
    markUnauthenticated()
  }, [markUnauthenticated])

  const value = useMemo(
    () => ({
      status,
      user,
      sessionExpiresAt,
      error,
      login,
      register,
      logout,
      restoreSession,
      updatePassword,
      exportData,
      removeAccount,
    }),
    [
      status,
      user,
      sessionExpiresAt,
      error,
      login,
      register,
      logout,
      restoreSession,
      updatePassword,
      exportData,
      removeAccount,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
