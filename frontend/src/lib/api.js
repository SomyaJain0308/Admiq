import { getAccessToken, setAccessToken, getRefreshToken, setRefreshToken, clearTokens } from "@/lib/tokenStore"

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

// Shared across every simultaneous 401 - see note above. Without this, two
// requests failing at the same moment would each try to use the same
// (single-use, rotating) refresh token, and the second one would always fail.
let refreshPromise = null

async function doRefresh() {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new ApiError("No refresh token available", 401, null)
  }
  const response = await fetch(`${API_BASE_URL}/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!response.ok) {
    clearTokens()
    throw new ApiError("Session expired, please log in again", 401, null)
  }
  const data = await response.json()
  setAccessToken(data.access_token)
  setRefreshToken(data.refresh_token)
  return data.access_token
}

function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

// Core request function. Every call goes through here so the 401-retry-once
// logic only has to be written and tested in one place.
async function request(path, options = {}, { skipAuth = false, isRetry = false } = {}) {
  const headers = { ...(options.headers || {}) }
  if (!skipAuth) {
    const token = getAccessToken()
    if (token) {
      headers["Authorization"] = `Bearer ${token}`
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })

  if (response.status === 401 && !skipAuth && !isRetry) {
    try {
      await refreshAccessToken()
    } catch {
      throw new ApiError("Session expired, please log in again", 401, null)
    }
    return request(path, options, { skipAuth, isRetry: true })
  }

  if (!response.ok) {
    let data = null
    try {
      data = await response.json()
    } catch {
      // response had no JSON body - fine, data stays null
    }
    throw new ApiError(data?.detail || `Request failed with status ${response.status}`, response.status, data)
  }

  if (response.status === 204) {
    return null
  }
  return response.json()
}

export const api = {
  get: (path) => request(path, { method: "GET" }),
  post: (path, body) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: "DELETE" }),

  // A handful of backend endpoints take plain, undecorated str/int/datetime
  // parameters that aren't part of the URL path - FastAPI treats those as
  // query params by default (only Pydantic-model parameters get read from
  // the request body). This helper is for exactly those endpoints - don't
  // use it for anything that expects real JSON.
  postWithQueryParams: (path, params) => {
    const search = new URLSearchParams(params).toString()
    return request(`${path}?${search}`, { method: "POST" })
  },

  // For multipart/form-data uploads (e.g. document files). Deliberately
  // does NOT set Content-Type - the browser sets it itself, including the
  // multipart boundary, and setting it manually here would break the upload.
  postFormData: (path, formData) => request(path, { method: "POST", body: formData }),

  // Auth endpoints need special handling: /token takes form-encoded data
  // (FastAPI's OAuth2PasswordRequestForm), not JSON like everything else.
  login: async (email, password) => {
    const body = new URLSearchParams()
    body.set("username", email)
    body.set("password", password)
    return request("/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body }, { skipAuth: true })
  },
  refresh: doRefresh,
  logout: (refreshToken) => request("/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refreshToken }) }, { skipAuth: true }),

  // Both intentionally skipAuth - the person isn't logged in yet when they
  // need these.
  forgotPassword: (staffEmail) =>
    request("/forgot-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ staff_email: staffEmail }) }, { skipAuth: true }),
  resetPassword: (token, newPassword) =>
    request("/reset-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token, new_password: newPassword }) }, { skipAuth: true }),

  // For file-download endpoints (CSV export) - these return a real file
  // body, not JSON, so they can't go through request()'s response.json().
  // Reuses the same token + one-retry-on-401 handling as everything else.
  downloadFile: async (path) => {
    const doFetch = () => {
      const token = getAccessToken()
      return fetch(`${API_BASE_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    }
    let response = await doFetch()
    if (response.status === 401) {
      try {
        await refreshAccessToken()
      } catch {
        throw new ApiError("Session expired, please log in again", 401, null)
      }
      response = await doFetch()
    }
    if (!response.ok) {
      throw new ApiError(`Request failed with status ${response.status}`, response.status, null)
    }
    const blob = await response.blob()
    const disposition = response.headers.get("Content-Disposition") || ""
    const match = disposition.match(/filename="?([^"]+)"?/)
    const filename = match ? match[1] : "export.csv"

    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  },
}
