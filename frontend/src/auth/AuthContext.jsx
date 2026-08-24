import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
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
  const [error, setError] = useState('')

  const markUnauthenticated = useCallback(() => {
    setUser(null)
    setError('')
    setStatus(AUTH_STATUS.UNAUTHENTICATED)
  }, [])

  const restoreSession = useCallback(async () => {
    setError('')
    setStatus(AUTH_STATUS.LOADING)
    try {
      const res = await getCurrentUser()
      setUser(res.user)
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

  const value = useMemo(
    () => ({ status, user, error, login, register, logout, restoreSession }),
    [status, user, error, login, register, logout, restoreSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
