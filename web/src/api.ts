// REST-клиент Mini App.

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

export async function authenticate(initData: string): Promise<AuthResponse> {
  const res = await fetch('/api/auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData }),
  })
  if (!res.ok) {
    throw new Error(`сервер ответил ${res.status}`)
  }
  return (await res.json()) as AuthResponse
}
