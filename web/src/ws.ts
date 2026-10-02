// WebSocket-клиент стола: переподключение с задержкой, пинг для живости.

import type { Snapshot } from './types'

export type TableOutMessage =
  | { type: 'sit'; seat: number }
  | { type: 'stand_up' }
  | { type: 'start_game' }
  | { type: 'end_game' }
  | { type: 'kick'; user_id: number }
  | { type: 'transfer_host'; user_id: number }
  | { type: 'action'; action: 'fold' | 'check' | 'call' | 'bet' | 'raise'; amount?: number }

export interface TableSocket {
  send(msg: TableOutMessage): void
  close(): void
}

interface Handlers {
  onState: (snapshot: Snapshot) => void
  onError?: (message: string) => void
}

const MAX_ATTEMPTS = 8

export function connectTableSocket(code: string, token: string, handlers: Handlers): TableSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws/table/${code}?token=${encodeURIComponent(token)}`

  let ws: WebSocket | null = null
  let closed = false
  let attempts = 0
  let retryTimer: number | undefined
  let pingTimer: number | undefined

  const open = () => {
    ws = new WebSocket(url)
    ws.onopen = () => {
      attempts = 0
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
      if (closed || ev.code === 4401) return
      attempts += 1
      if (attempts > MAX_ATTEMPTS) {
        handlers.onError?.('соединение потеряно')
        return
      }
      retryTimer = window.setTimeout(open, Math.min(1000 * attempts, 5000))
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
