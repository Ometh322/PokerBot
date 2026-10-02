// Место за столом: аватар, стек, ставка, бейджи, таймер-ободок.

import PlayingCard from './PlayingCard'
import type { HandPlayerInfo, PlayerInfo } from '../types'

interface Props {
  player: PlayerInfo
  hand?: HandPlayerInfo
  isDealer: boolean
  isToAct: boolean
  timeFrac: number | null // 0..1 остаток таймера
  revealedCards?: string[]
  isMe: boolean
}

export default function SeatView({
  player,
  hand,
  isDealer,
  isToAct,
  timeFrac,
  revealedCards,
  isMe,
}: Props) {
  const folded = hand?.folded ?? false
  const ringStyle =
    isToAct && timeFrac !== null
      ? ({ '--frac': String(timeFrac) } as React.CSSProperties)
      : undefined

  return (
    <div className={`seat ${folded ? 'seat-folded' : ''} ${isToAct ? 'seat-active' : ''}`}>
      {isDealer && <span className="badge badge-d">D</span>}
      <div
        className={`avatar-ring ${isToAct && timeFrac !== null ? 'ring-timer' : ''} ${
          isToAct && timeFrac === null ? 'ring-glow' : ''
        }`}
        style={ringStyle}
      >
        {player.photo_url ? (
          <img className="avatar avatar-sm" src={player.photo_url} alt="" />
        ) : (
          <div className="avatar avatar-sm avatar-placeholder">
            {player.name.slice(0, 1)}
          </div>
        )}
      </div>
      <div className="seat-name" title={player.name}>
        {isMe ? 'Ты' : player.name}
      </div>
      <div className="seat-stack">{hand ? hand.stack : player.stack}</div>
      {hand && hand.bet > 0 && <div className="bet-chip">💰 {hand.bet}</div>}
      {hand?.all_in && <div className="allin-tag">ALL IN</div>}
      {revealedCards && revealedCards.length > 0 && (
        <div className="mini-cards">
          {revealedCards.map((c) => (
            <PlayingCard key={c} code={c} small />
          ))}
        </div>
      )}
    </div>
  )
}
