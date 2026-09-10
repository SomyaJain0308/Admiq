import { useEffect, useState, useCallback } from "react"
import { api } from "@/lib/api"
import { setTokens, getRefreshToken, clearTokens } from "@/lib/tokenStore"
import { AuthContext } from "@/context/auth-context"

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
      // Nothing to restore if there's no refresh token in localStorage
      // (first visit, or a previous logout/expiry already cleared it) -
      // skip straight to "logged out" instead of firing a /refresh request
      // that's guaranteed to fail.
      if (!getRefreshToken()) {
        setIsBootstrapping(false)
        return
      }
      try {
        // api.refresh() (doRefresh) already stores both the new access and
        // refresh tokens itself before returning - nothing more to set here.
        await api.refresh()
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
    setTokens(data)
    await fetchCurrentUser()
  }, [fetchCurrentUser])

  const logout = useCallback(async () => {
    try {
      await api.logout()
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
