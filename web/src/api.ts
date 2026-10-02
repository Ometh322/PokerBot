// REST-клиент Mini App.

import type { HandSummary, Settlement, Snapshot, TableSettings, TableSummary } from './types'

export interface AuthUser {
  id: number
  first_name: string
  last_name?: string | null
  username?: string | null
  photo_url?: string | null
}

export interface AuthResponse {
  user: AuthUser
  token: string
  start_param?: string | null
}

export class ApiError extends Error {}

async function request<T>(
  path: string,
  method: string,
  token: string | null,
  body?: unknown,
): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let message = `сервер ответил ${res.status}`
    try {
      const data: unknown = await res.json()
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') {
        message = detail
      } else if (Array.isArray(detail) && detail.length > 0) {
        message = String((detail[0] as { msg?: unknown }).msg ?? message)
      }
    } catch {
      // тело не JSON — оставляем статус
    }
    throw new ApiError(message)
  }
  return (await res.json()) as T
}

export function authenticate(initData: string): Promise<AuthResponse> {
  return request<AuthResponse>('/api/auth', 'POST', null, { init_data: initData })
}

export function devAuth(userId: number, firstName: string): Promise<AuthResponse> {
  return request<AuthResponse>('/api/auth/dev', 'POST', null, {
    user_id: userId,
    first_name: firstName,
  })
}

export function fetchTables(token: string): Promise<TableSummary[]> {
  return request<TableSummary[]>('/api/tables', 'GET', token)
}

export function createTable(
  token: string,
  payload: { name: string; settings: TableSettings },
): Promise<{ code: string; invite_link: string; snapshot: Snapshot }> {
  return request('/api/tables', 'POST', token, payload)
}

export function fetchTable(token: string, code: string): Promise<Snapshot> {
  return request<Snapshot>(`/api/tables/${code}`, 'GET', token)
}

export function fetchSettlement(token: string, code: string): Promise<Settlement> {
  return request<Settlement>(`/api/tables/${code}/settlement`, 'GET', token)
}

export function fetchHands(
  token: string,
  code: string,
  limit = 20,
): Promise<HandSummary[]> {
  return request<HandSummary[]>(`/api/tables/${code}/hands?limit=${limit}`, 'GET', token)
}
