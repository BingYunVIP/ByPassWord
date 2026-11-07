/**
 * 统一 API 客户端：自动带 token、401 自动刷新一次、错误结构归一化。
 */

const BASE = '/api'

let accessToken = null
let refreshHandler = null
let unauthorizedHandler = null
let refreshInFlight = null

export class ApiError extends Error {
  constructor(status, code, message, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }
}

export function setAccessToken(token) {
  accessToken = token
}

export function setUnauthorizedHandler(handler) { unauthorizedHandler = handler }

/** 由 auth store 注入：返回 true 表示刷新成功，可以重试原请求 */
export function setRefreshHandler(handler) {
  refreshHandler = handler
}

async function parseResponse(response) {
  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { raw: text }
    }
  }
  if (!response.ok) {
    const error = data?.error || {}
    throw new ApiError(
      response.status,
      error.code || 'http_error',
      error.message || `请求失败（${response.status}）`,
      error.detail ?? null
    )
  }
  return data
}

/**
 * @param {string} path 以 / 开头，如 '/vault'
 * @param {{method?:string, body?:any, auth?:boolean, retry?:boolean}} options
 */
export async function apiFetch(path, options = {}) {
  const { method = 'GET', body, auth = true, retry = true } = options

  const requestToken = accessToken
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth && requestToken) headers.Authorization = `Bearer ${requestToken}`

  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body === undefined ? undefined : JSON.stringify(body)
  })

  const failure = response.status === 401 ? await response.clone().json().catch(() => null) : null
  const rejectedInput = ['invalid_credentials', 'invalid_code', 'invalid_recovery_code'].includes(failure?.error?.code)
  if (response.status === 401 && auth && requestToken === accessToken && !rejectedInput && retry && refreshHandler) {
    if (!refreshInFlight) refreshInFlight = Promise.resolve(refreshHandler()).finally(() => { refreshInFlight = null })
    const refreshed = await refreshInFlight
    if (refreshed) {
      return apiFetch(path, { method, body, auth, retry: false })
    }
  }

  if (response.status === 401 && auth && requestToken === accessToken && !rejectedInput) unauthorizedHandler?.()
  return parseResponse(response)
}
