import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchTable, type AuthResponse } from '../api'
import { connectTableSocket, type TableOutMessage, type TableSocket } from '../ws'
import { chipLabel, rebuyLabel, statusLabel } from '../ui'
import type { PlayerInfo, Snapshot } from '../types'

const tg = window.Telegram?.WebApp

interface Props {
  code: string
  auth: AuthResponse
  onExit: () => void
}

export default function TableLobby({ code, auth, onExit }: Props) {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const sockRef = useRef<TableSocket | null>(null)

  useEffect(() => {
    // Первый снапшот по REST — экран рисуется сразу, WS догонит изменениями.
    fetchTable(auth.token, code).catch(() => undefined)
    const sock = connectTableSocket(code, auth.token, {
      onState: (state) => setSnap(state),
      onError: (message) => {
        setError(message)
        window.setTimeout(() => setError(''), 4000)
      },
    })
    sockRef.current = sock
    return () => sock.close()
  }, [auth.token, code])

  const send = (msg: TableOutMessage) => {
    tg?.HapticFeedback?.impactOccurred('light')
    sockRef.current?.send(msg)
  }

  const seatMap = useMemo(() => {
    const map = new Map<number, PlayerInfo>()
    snap?.players.forEach((p) => map.set(p.seat, p))
    return map
  }, [snap])

  if (snap === null) {
    return (
      <div className="app">
        <div className="panel loading">{error ? `Ошибка: ${error}` : 'Открываем стол…'}</div>
      </div>
    )
  }

  const isHost = snap.you.is_host
  const seated = snap.you.seat !== null
  const seats = Array.from({ length: snap.seats_total }, (_, i) => i)

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(snap.invite_link)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard недоступен — ссылку видно в шэре
    }
  }

  const share = () => {
    const url =
      'https://t.me/share/url' +
      `?url=${encodeURIComponent(snap.invite_link)}` +
      `&text=${encodeURIComponent('Садимся за покерный стол 🃏')}`
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(url)
    } else {
      void copyInvite()
    }
  }

  return (
    <div className="app">
      <div className="topbar">
        <button className="btn-ghost" onClick={onExit}>
          ← Мои столы
        </button>
        <span className={`status-chip status-${snap.status}`}>{statusLabel(snap.status)}</span>
      </div>

      <section className="panel">
        <h2 className="table-name">{snap.name}</h2>
        <div className="settings-line">
          💰 {snap.settings.starting_stack} · 🌐 {snap.settings.small_blind}/{snap.settings.big_blind} ·{' '}
          {chipLabel(snap.settings.chip_value)} · {rebuyLabel(snap.settings.rebuy_mode)} · 👥{' '}
          {snap.players.length}/{snap.seats_total} · код {snap.code}
        </div>
        <div className="invite-row">
          <button className="btn-primary btn-sm" onClick={share}>
            📨 Пригласить друзей
          </button>
          <button className="btn-secondary" onClick={() => void copyInvite()}>
            {copied ? '✓ Скопировано' : '🔗 Копировать'}
          </button>
        </div>
      </section>

      {error && <div className="panel error-banner">{error}</div>}

      {snap.status !== 'finished' && (
        <section className="panel">
          <h3 className="section-title">Места</h3>
          <div className="seat-grid">
            {seats.map((seat) => {
              const player = seatMap.get(seat)
              if (player) {
                return (
                  <div
                    key={seat}
                    className={`seat-card ${player.user_id === auth.user.id ? 'seat-mine' : ''}`}
                  >
                    <span className="seat-no">#{seat + 1}</span>
                    {player.photo_url ? (
                      <img className="avatar avatar-sm" src={player.photo_url} alt="" />
                    ) : (
                      <div className="avatar avatar-sm avatar-placeholder">
                        {player.name.slice(0, 1)}
                      </div>
                    )}
                    <div className="seat-name">
                      {player.is_host ? '👑 ' : ''}
                      {player.name}
                    </div>
                    <div className="seat-stack">{player.stack}</div>
                    {isHost && player.user_id !== auth.user.id && snap.status === 'lobby' && (
                      <div className="seat-actions">
                        <button
                          className="link-btn"
                          onClick={() => send({ type: 'kick', user_id: player.user_id })}
                        >
                          исключить
                        </button>
                        <button
                          className="link-btn"
                          onClick={() => send({ type: 'transfer_host', user_id: player.user_id })}
                        >
                          сделать хостом
                        </button>
                      </div>
                    )}
                  </div>
                )
              }
              return (
                <button
                  key={seat}
                  className="seat-empty"
                  disabled={seated || snap.status !== 'lobby'}
                  onClick={() => send({ type: 'sit', seat })}
                >
                  <span className="seat-no">#{seat + 1}</span>
                  <span>{seated ? '—' : 'Сесть'}</span>
                </button>
              )
            })}
          </div>
        </section>
      )}

      <section className="panel actions-panel">
        {snap.status === 'lobby' &&
          (seated ? (
            <button className="btn-secondary" onClick={() => send({ type: 'stand_up' })}>
              🚪 Встать
            </button>
          ) : (
            <p className="hint">Сядь на свободное место, чтобы играть</p>
          ))}
        {snap.status === 'lobby' && isHost && (
          <button
            className="btn-primary"
            disabled={snap.players.length < 2}
            onClick={() => send({ type: 'start_game' })}
          >
            ▶️ Начать игру{snap.players.length < 2 ? ' — нужно 2+ игроков' : ''}
          </button>
        )}
        {snap.status === 'active' && (
          <>
            <div className="info-banner">
              🚧 Игра началась! Раздачи карт подключим в фазе M3 — пока стол «разогревается».
            </div>
            {isHost && (
              <button className="btn-danger" onClick={() => send({ type: 'end_game' })}>
                🏁 Завершить игру
              </button>
            )}
          </>
        )}
        {snap.status === 'finished' && (
          <>
            <div className="info-banner">
              🏁 Сессия завершена. Расчёт долгов появится в фазе M5.
            </div>
            <button className="btn-secondary" onClick={onExit}>
              ← На главную
            </button>
          </>
        )}
      </section>
    </div>
  )
}
