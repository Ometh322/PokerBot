// WebSocket-клиент стола: бесконечное переподключение, пинг для живости.
//
// Туннель время от времени ротируется (вахта пересоздаёт его за ~20 с на
// том же адресе) — клиент терпеливо ретраит до успеха, игра на сервере
// тем временем не останавливается. onError используется только для
// содержательных ошибок (авторизация, действия сервера).

import type { Snapshot } from './types'

export type TableOutMessage =
  | { type: 'sit'; seat: number }
  | { type: 'stand_up' }
  | { type: 'start_game' }
  | { type: 'end_game' }
  | { type: 'kick'; user_id: number }
  | { type: 'transfer_host'; user_id: number }
  | { type: 'rebuy' }
  | { type: 'action'; action: 'fold' | 'check' | 'call' | 'bet' | 'raise'; amount?: number }

export interface TableSocket {
  send(msg: TableOutMessage): void
  close(): void
}

interface Handlers {
  onState: (snapshot: Snapshot) => void
  onError?: (message: string) => void
  onReconnecting?: (lost: boolean) => void // true — связь потеряна, ретраим
}

const NOTIFY_AFTER_FAILURES = 3
const MAX_BACKOFF = 5000

export function connectTableSocket(code: string, token: string, handlers: Handlers): TableSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws/table/${code}?token=${encodeURIComponent(token)}`

  let ws: WebSocket | null = null
  let closed = false
  let failures = 0
  let retryTimer: number | undefined
  let pingTimer: number | undefined

  const open = () => {
    ws = new WebSocket(url)
    ws.onopen = () => {
      if (failures >= NOTIFY_AFTER_FAILURES) handlers.onReconnecting?.(false)
      failures = 0
      pingTimer = window.setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send('{"type":"ping"}')
      }, 25000)
    }
    ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string) as { type?: string; state?: Snapshot; message?: string }
        if (msg?.type === 'state' && msg.state) handlers.onState(msg.state)
        else if (msg?.type === 'error') handlers.onError?.(msg.message ?? 'ошибка')
      } catch {
        // битое сообщение игнорируем
      }
    }
    ws.onclose = (ev: CloseEvent) => {
      window.clearInterval(pingTimer)
      if (closed || ev.code === 4401) return // 4401 — нет авторизации, ретраить бессмысленно
      failures += 1
      if (failures === NOTIFY_AFTER_FAILURES) {
        handlers.onReconnecting?.(true)
      }
      retryTimer = window.setTimeout(open, Math.min(500 * failures, MAX_BACKOFF))
    }
    ws.onerror = () => {
      // обработка — в onclose (следует за onerror)
    }
  }

  open()

  return {
    send: (msg: TableOutMessage) => {
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
    },
    close: () => {
      closed = true
      window.clearTimeout(retryTimer)
      window.clearInterval(pingTimer)
      ws?.close()
    },
  }
}
