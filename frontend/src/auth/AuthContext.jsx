import {
  createContext,
  useCallback,
  useContext,
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
import { AUTH_STATUS } from '../api/constants'

const UNAUTHORIZED_EVENT = 'yoko:unauthorized'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(AUTH_STATUS.LOADING)
  const [user, setUser] = useState(null)

  const markUnauthenticated = useCallback(() => {
    setUser(null)
    setStatus(AUTH_STATUS.UNAUTHENTICATED)
  }, [])

  // 启动/刷新时用 Cookie 调 /me 恢复登录状态
  useEffect(() => {
    let alive = true
    getCurrentUser()
      .then((res) => {
        if (!alive) return
        setUser(res.user)
        setStatus(AUTH_STATUS.AUTHENTICATED)
      })
      .catch(() => {
        // Cookie 缺失、Session 过期或网络失败都回到登录页
        if (!alive) return
        markUnauthenticated()
      })
    return () => {
      alive = false
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
    } finally {
      markUnauthenticated()
    }
  }, [markUnauthenticated])

  const value = useMemo(
    () => ({ status, user, login, register, logout }),
    [status, user, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}