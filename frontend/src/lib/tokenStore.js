// Access token: in-memory only, gone on every page reload by design (limits
// the damage window if something ever reads it off the page).
//
// Refresh token: the backend hands this back as a plain field in the /token
// and /refresh JSON response bodies (schemas/staff.py's Token model) and
// expects it back the same way - as { refresh_token } in the POST body of
// /refresh and /logout (RefreshTokenRequest) - not as an httpOnly cookie.
// So unlike the access token, this one has to be persisted somewhere JS can
// read it back after a reload, or a refreshed page could never silently
// restore a session. localStorage is the standard tradeoff here: it
// survives a reload (unlike memory) without needing a cookie the backend
// doesn't set.
const REFRESH_TOKEN_KEY = "admiq-refresh-token"

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
  try {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  } catch {
    // Storage can throw in private-browsing/locked-down environments -
    // treat that the same as "no refresh token", not a crash.
    return null
  }
}

function setRefreshToken(token) {
  try {
    if (token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, token)
    } else {
      localStorage.removeItem(REFRESH_TOKEN_KEY)
    }
  } catch {
    // If storage isn't available the session just won't survive a reload -
    // a safe degradation, not worth surfacing to the user.
  }
}

// Single entry point for storing what /token and /refresh return, so every
// call site sets both tokens together instead of risking one getting
// updated without the other.
export function setTokens({ access_token, refresh_token } = {}) {
  setAccessToken(access_token ?? null)
  setRefreshToken(refresh_token ?? null)
}

export function clearTokens() {
  setAccessToken(null)
  setRefreshToken(null)
}
