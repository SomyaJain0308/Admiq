import { createContext, useContext, useEffect, useState, useCallback } from "react"
import { api } from "@/lib/api"
import { setAccessToken, getRefreshToken, setRefreshToken, clearTokens } from "@/lib/tokenStore"

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // isBootstrapping: true only during the very first check on page load, while
  // we attempt to silently restore a session from the persisted refresh token.
  // Everything that renders "you must log in" needs to wait for this to
  // finish, or it'll flash a login screen for a split second on every reload
  // even for an already-logged-in staff member.
  const [isBootstrapping, setIsBootstrapping] = useState(true)

  const fetchCurrentUser = useCallback(async () => {
    const me = await api.get("/me")
    setUser(me)
    return me
  }, [])

  useEffect(() => {
    async function bootstrap() {
      const refreshToken = getRefreshToken()
      if (!refreshToken) {
        setIsBootstrapping(false)
        return
      }
      try {
        const data = await api.refresh()
        setAccessToken(data.access_token)
        await fetchCurrentUser()
      } catch {
        clearTokens()
        setUser(null)
      } finally {
        setIsBootstrapping(false)
      }
    }
    bootstrap()
  }, [fetchCurrentUser])

  const login = useCallback(async (email, password) => {
    const data = await api.login(email, password)
    setAccessToken(data.access_token)
    setRefreshToken(data.refresh_token)
    await fetchCurrentUser()
  }, [fetchCurrentUser])

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken()
    try {
      if (refreshToken) {
        await api.logout(refreshToken)
      }
    } catch {
      // Even if the server call fails (e.g. token already expired), we still
      // want to clear local state below - logging out should never get a
      // user "stuck" logged in on their own device.
    }
    clearTokens()
    setUser(null)
  }, [])

  const value = {
    user,
    isAuthenticated: !!user,
    isBootstrapping,
    login,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return ctx
}
