// История раздач: борд, банк, победители с комбинациями.

import { useState } from 'react'
import { fetchHands } from '../api'
import type { HandSummary } from '../types'
import PlayingCard from './PlayingCard'

interface Props {
  code: string
  token: string
}

export default function HandHistory({ code, token }: Props) {
  const [open, setOpen] = useState(false)
  const [hands, setHands] = useState<HandSummary[] | null>(null)
  const [error, setError] = useState('')

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next && hands === null) {
      try {
        setHands(await fetchHands(token, code, 30))
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
    }
  }

  return (
    <section className="panel">
      <button className="btn-ghost history-toggle" onClick={() => void toggle()}>
        {open ? '▾' : '▸'} 📜 История раздач{hands ? ` (${hands.length})` : ''}
      </button>
      {open &&
        (error ? (
          <div className="panel error-banner">{error}</div>
        ) : hands === null ? (
          <div className="loading history-loading">Загружаем…</div>
        ) : hands.length === 0 ? (
          <p className="hint">Раздач ещё не было</p>
        ) : (
          <div className="hand-list">
            {hands.map((h) => (
              <div key={h.number} className="hand-row">
                <span className="hand-no">№{h.number}</span>
                <div className="hand-board">
                  {h.board.map((c) => (
                    <PlayingCard key={c} code={c} small />
                  ))}
                </div>
                <div className="hand-meta">
                  банк {h.pot_total} · 🏆{' '}
                  {h.winners
                    .map((w) => `${w.name} +${w.amount}${w.hand ? ` (${w.hand})` : ''}`)
                    .join(', ')}
                </div>
              </div>
            ))}
          </div>
        ))}
    </section>
  )
}
