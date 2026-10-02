// Панель действий: фолд/чек/колл + бет-рейз со слайдером и пресетами.

import { useEffect, useState } from 'react'
import type { LegalActions } from '../types'

interface Props {
  legal: LegalActions
  pot: number
  currentBet: number
  step: number
  onAction: (action: 'fold' | 'check' | 'call' | 'bet' | 'raise', amount?: number) => void
}

export default function ActionBar({ legal, pot, currentBet, step, onAction }: Props) {
  const range = legal.raise_to
  const [amount, setAmount] = useState<number>(range ? range[0] : 0)

  useEffect(() => {
    setAmount(range ? range[0] : 0)
  }, [range ? range[0] : 0, range ? range[1] : 0, legal.call])

  if (!range) {
    return (
      <div className="action-bar">
        <button className="ab-btn ab-fold" onClick={() => onAction('fold')}>
          ФОЛД
        </button>
        {legal.check ? (
          <button className="ab-btn ab-check" onClick={() => onAction('check')}>
            ЧЕК
          </button>
        ) : (
          <button className="ab-btn ab-check" onClick={() => onAction('call')}>
            КОЛЛ {legal.call}
          </button>
        )}
      </div>
    )
  }

  const [min, max] = range
  const clamp = (v: number) => Math.min(max, Math.max(min, v))
  const round = (v: number) => clamp(Math.round(v / step) * step)
  const presets = [
    { label: 'мин', value: min },
    { label: '½', value: round(pot / 2) },
    { label: 'банк', value: round(pot) },
    { label: 'всё', value: max },
  ].filter((p, i, arr) => arr.findIndex((q) => q.value === p.value) === i)

  const label = currentBet > 0 ? 'РЕЙЗ' : 'БЕТ'

  return (
    <div className="action-bar">
      <div className="ab-row">
        <button className="ab-btn ab-fold" onClick={() => onAction('fold')}>
          ФОЛД
        </button>
        {legal.check ? (
          <button className="ab-btn ab-check" onClick={() => onAction('check')}>
            ЧЕК
          </button>
        ) : (
          <button className="ab-btn ab-check" onClick={() => onAction('call')}>
            КОЛЛ {legal.call}
          </button>
        )}
      </div>
      <div className="raise-box">
        <div className="raise-top">
          <span className="raise-amount">{amount}</span>
          <div className="raise-presets">
            {presets.map((p) => (
              <button
                key={p.label}
                type="button"
                className={`preset ${amount === p.value ? 'preset-active' : ''}`}
                onClick={() => setAmount(p.value)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <input
          className="raise-slider"
          type="range"
          min={min}
          max={max}
          step={step}
          value={amount}
          onChange={(e) => setAmount(Number(e.target.value))}
        />
        <button className="ab-btn ab-raise" onClick={() => onAction('raise', amount)}>
          {label} {amount}
          {amount === max ? ' (олл-ин)' : ''}
        </button>
      </div>
    </div>
  )
}
