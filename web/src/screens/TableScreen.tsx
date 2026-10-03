import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { fetchTable, type AuthResponse } from '../api'
import { connectTableSocket, type TableOutMessage, type TableSocket } from '../ws'
import { chipLabel, rebuyLabel, statusLabel } from '../ui'
import { playDeal, playTurn, playWin, soundEnabled, toggleSound } from '../sound'
import type { PlayerInfo, Snapshot } from '../types'
import PlayingCard from '../components/PlayingCard'
import SeatView from '../components/SeatView'
import ActionBar from '../components/ActionBar'
import Settlement from '../components/Settlement'
import HandHistory from '../components/HandHistory'

const tg = window.Telegram?.WebApp

interface Props {
  code: string
  auth: AuthResponse
  onExit: () => void
}

export default function TableScreen({ code, auth, onExit }: Props) {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [now, setNow] = useState(() => Date.now() / 1000)
  const [soundOn, setSoundOn] = useState(() => soundEnabled())
  const sockRef = useRef<TableSocket | null>(null)

  useEffect(() => {
    fetchTable(auth.token, code).then(setSnap).catch(() => undefined)
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

  const hand = snap?.hand ?? null
  const live = hand !== null && hand.street !== null

  // Тик для таймеров и обратного отсчёта следующей раздачи.
  useEffect(() => {
    if (!live && hand?.next_hand_at == null) return
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 500)
    return () => window.clearInterval(timer)
  }, [live, hand?.next_hand_at])

  // Звуки и хаптика: новая карта на борде, мой ход, победа в раздаче.
  const boardLen = hand?.board.length ?? 0
  useEffect(() => {
    if (boardLen > 0) playDeal()
  }, [boardLen])

  const myTurn = Boolean(snap?.you.legal_actions)
  useEffect(() => {
    if (myTurn) playTurn()
  }, [myTurn])

  const lastResult = hand?.last_result ?? null
  useEffect(() => {
    if (!lastResult) return
    if (lastResult.winners.some((w) => w.user_id === auth.user.id)) {
      playWin()
      tg?.HapticFeedback?.notificationOccurred('success')
    }
  }, [lastResult, auth.user.id])

  const send = (msg: TableOutMessage) => {
    tg?.HapticFeedback?.impactOccurred('light')
    sockRef.current?.send(msg)
  }

  const sendAction: React.ComponentProps<typeof ActionBar>['onAction'] = (action, amount) => {
    tg?.HapticFeedback?.impactOccurred('medium')
    sockRef.current?.send({ type: 'action', action, amount })
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

  const me = snap.players.find((p) => p.user_id === auth.user.id)
  const mySeat = snap.you.seat
  const isHost = snap.you.is_host
  const seats = Array.from({ length: snap.seats_total }, (_, i) => i)
  const toActName = hand?.to_act
    ? snap.players.find((p) => p.user_id === hand.to_act)?.name
    : null
  const nameOf = (uid: number) =>
    snap.players.find((p) => p.user_id === uid)?.name ?? `Игрок ${uid}`

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
        <div className="topbar-right">
          <button
            className="btn-ghost"
            onClick={() => {
              toggleSound()
              setSoundOn(soundEnabled())
            }}
            title="Звуки"
          >
            {soundOn ? '🔊' : '🔇'}
          </button>
          <span className={`status-chip status-${snap.status}`}>{statusLabel(snap.status)}</span>
        </div>
      </div>

      <div className="table-line">
        <span className="tname">{snap.name}</span>
        <span className="tmeta">
          🌐 {snap.settings.small_blind}/{snap.settings.big_blind} · {chipLabel(snap.settings.chip_value)}
        </span>
      </div>

      {error && <div className="panel error-banner">{error}</div>}

      {snap.status === 'lobby' && (
        <>
          <section className="panel">
            <div className="settings-line">
              💰 {snap.settings.starting_stack} · {rebuyLabel(snap.settings.rebuy_mode)} · 👥{' '}
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
                    disabled={mySeat !== null}
                    onClick={() => send({ type: 'sit', seat })}
                  >
                    <span className="seat-no">#{seat + 1}</span>
                    <span>{mySeat !== null ? '—' : 'Сесть'}</span>
                  </button>
                )
              })}
            </div>
          </section>

          <section className="panel actions-panel">
            {mySeat !== null ? (
              <button className="btn-secondary" onClick={() => send({ type: 'stand_up' })}>
                🚪 Встать
              </button>
            ) : (
              <p className="hint">Сядь на свободное место, чтобы играть</p>
            )}
            {isHost && (
              <button
                className="btn-primary"
                disabled={snap.players.length < 2}
                onClick={() => send({ type: 'start_game' })}
              >
                ▶️ Начать игру{snap.players.length < 2 ? ' — нужно 2+ игроков' : ''}
              </button>
            )}
          </section>
        </>
      )}

      {snap.status === 'active' && hand && (
        <>
          <div className="felt-area">
            <div className="felt">
              <div className="pot-label" key={hand.pot}>
                {live ? `Банк ${hand.pot}` : `Раздача #${hand.number}`}
              </div>
              <div className="board">
                {Array.from({ length: 5 }, (_, i) =>
                  hand.board[i] ? (
                    <PlayingCard key={i} code={hand.board[i]} flip />
                  ) : (
                    <div key={i} className="pcard pcard-slot" />
                  ),
                )}
              </div>
              {hand.last_result && (
                <div className="result-lines">
                  {hand.last_result.winners.map((w) => (
                    <div key={w.user_id} className="result-line">
                      🏆 {nameOf(w.user_id)} +{w.amount}
                      {w.hand ? ` — ${w.hand}` : ''}
                    </div>
                  ))}
                </div>
              )}
              {hand.waiting && (
                <div className="waiting-note">
                  Ждём игроков со стеком: сделай ребай или позови ещё друзей
                </div>
              )}
            </div>

            {seats.map((seat) => {
              const player = seatMap.get(seat)
              if (!player) return null
              const hp = hand.players.find((p) => p.user_id === player.user_id)
              const revealed = hand.revealed[String(player.user_id)]
              const isToAct = hand.to_act === player.user_id
              let timeFrac: number | null = null
              if (isToAct && hand.deadline != null && snap.settings.action_timeout) {
                timeFrac = Math.max(
                  0,
                  Math.min(1, (hand.deadline - now) / snap.settings.action_timeout),
                )
              }
              const shifted = (seat - (mySeat ?? 0) + seats.length) % seats.length
              const angle = Math.PI / 2 + (2 * Math.PI * shifted) / seats.length
              const x = 50 + 45 * Math.cos(angle)
              const y = 50 + 43 * Math.sin(angle)
              const isWinner = Boolean(
                !live &&
                  hand.last_result?.winners.some((w) => w.user_id === player.user_id),
              )
              // Ставка — на сукне, на полпути от игрока к центру стола.
              const betX = 50 + (x - 50) * 0.5
              const betY = 46 + (y - 46) * 0.5
              return (
                <Fragment key={seat}>
                  <div
                    className="seat-pos"
                    style={{ left: `${x}%`, top: `${y}%` }}
                  >
                    <SeatView
                      player={player}
                      hand={hp}
                      isDealer={hand.dealer_seat === seat}
                      isToAct={isToAct}
                      timeFrac={timeFrac}
                      revealedCards={revealed}
                      isMe={player.user_id === auth.user.id}
                      isWinner={isWinner}
                      waiting={live && !hp}
                    />
                  </div>
                  {hp && hp.bet > 0 && (
                    <div
                      className="bet-pos"
                      style={{ left: `${betX}%`, top: `${betY}%` }}
                    >
                      <span className="bet-chip" key={hp.bet}>
                        💰 {hp.bet}
                      </span>
                    </div>
                  )}
                </Fragment>
              )
            })}
          </div>

          {snap.status === 'active' && hand && mySeat === null && (
            <section className="panel">
              <h3 className="section-title">Присоединиться к игре</h3>
              <div className="seat-grid">
                {seats
                  .filter((seat) => !seatMap.has(seat))
                  .map((seat) => (
                    <button
                      key={seat}
                      className="seat-empty"
                      onClick={() => send({ type: 'sit', seat })}
                    >
                      <span className="seat-no">#{seat + 1}</span>
                      <span>Сесть</span>
                    </button>
                  ))}
              </div>
              <p className="hint">
                Вход со стартовым стеком {snap.settings.starting_stack} — вступишь в
                игру с ближайшей раздачи, текущую досмотришь
              </p>
            </section>
          )}

          <div className="my-zone">
            {snap.you.rebuy_available && (
              <button className="btn-primary" onClick={() => send({ type: 'rebuy' })}>
                ♻️ Ребай +{snap.settings.starting_stack}
              </button>
            )}
            {snap.you.cards && snap.you.cards.length > 0 ? (
              <>
                <div className={`my-cards ${(hand.players.find((p) => p.user_id === auth.user.id)?.folded) ? 'my-cards-folded' : ''}`}>
                  {snap.you.cards.map((c) => (
                    <PlayingCard key={c} code={c} />
                  ))}
                </div>
                {snap.you.hand_hint && <div className="hand-hint">{snap.you.hand_hint}</div>}
              </>
            ) : (
              <div className="my-cards my-cards-empty">
                {me
                  ? live
                    ? 'Ты за столом — вступишь в игру со следующей раздачи…'
                    : 'Ждём следующую раздачу…'
                  : 'Ты наблюдаешь за игрой'}
              </div>
            )}

            {snap.you.legal_actions ? (
              <ActionBar
                legal={snap.you.legal_actions}
                pot={hand.pot}
                currentBet={hand.current_bet}
                step={snap.settings.small_blind}
                onAction={sendAction}
              />
            ) : (
              <div className="waiting-line">
                {hand.street === 'showdown' && !hand.last_result
                  ? '🔍 Вскрываем карты…'
                  : hand.next_hand_at != null
                    ? `Следующая раздача через ${Math.max(1, Math.ceil(hand.next_hand_at - now))} с…`
                    : toActName
                      ? `Ход: ${toActName === me?.name ? 'твой' : toActName}…`
                      : 'Раздача идёт…'}
              </div>
            )}

            {isHost && (
              <button className="btn-ghost btn-center" onClick={() => send({ type: 'end_game' })}>
                🏁 Завершить игру
              </button>
            )}
            {me && !live && hand.next_hand_at == null && (
              <button className="btn-ghost btn-center" onClick={() => send({ type: 'stand_up' })}>
                🚪 Встать из-за стола
              </button>
            )}
          </div>
        </>
      )}

      {snap.status !== 'lobby' && <HandHistory code={snap.code} token={auth.token} />}

      {snap.status === 'finished' && (
        <>
          <Settlement code={snap.code} token={auth.token} />
          <button className="btn-secondary" onClick={onExit}>
            ← На главную
          </button>
        </>
      )}
    </div>
  )
}
