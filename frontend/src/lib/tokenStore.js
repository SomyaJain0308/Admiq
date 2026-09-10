// Access token lives ONLY in memory - never persisted, gone on every page
// reload by design (limits the damage window if something ever reads it off
// the page). The refresh token now lives in an httpOnly cookie set by the
// backend (see staff.py's _set_refresh_token_cookie) - it's never readable
// from JS, so there's nothing to store or clear here for it. The browser
// sends it automatically on requests made with credentials: "include".

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

export function clearTokens() {
  setAccessToken(null)
}
