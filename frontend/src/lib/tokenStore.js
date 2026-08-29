// Access token lives ONLY in memory - never persisted, gone on every page
// reload by design (limits the damage window if something ever reads it off
// the page). Refresh token lives in localStorage so the session survives a
// reload; this is a deliberate simplification matching the backend, which
// currently returns the refresh token in the JSON response body rather than
// setting it as an httpOnly cookie. Moving to httpOnly cookies later would
// remove the localStorage/XSS exposure - worth doing before this ships to
// real users, not required to get the app working.

const REFRESH_TOKEN_KEY = "admiq_refresh_token"

let accessToken = null
const listeners = new Set()

export function getAccessToken() {
  return accessToken
}

export function setAccessToken(token) {
  accessToken = token
  listeners.forEach((fn) => fn(token))
}

export function subscribeToAccessToken(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setRefreshToken(token) {
  if (token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, token)
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }
}

export function clearTokens() {
  setAccessToken(null)
  setRefreshToken(null)
}
