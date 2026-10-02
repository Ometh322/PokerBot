// Экран расчёта: итоги сессии и минимальные переводы долгов.

import { useEffect, useState } from 'react'
import { fetchSettlement } from '../api'
import type { Settlement as SettlementData } from '../types'

const tg = window.Telegram?.WebApp

function formatCents(cents: number): string {
  if (cents % 100 === 0) return `${cents / 100} ₽`
  return `${(cents / 100).toFixed(2).replace('.', ',')} ₽`
}

function signedCents(cents: number): string {
  return cents > 0 ? `+${formatCents(cents)}` : formatCents(cents)
}

function signedChips(chips: number): string {
  return chips > 0 ? `+${chips}` : String(chips)
}

interface Props {
  code: string
  token: string
}

export default function Settlement({ code, token }: Props) {
  const [data, setData] = useState<SettlementData | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    fetchSettlement(token, code)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [token, code])

  if (error) return <div className="panel error-banner">{error}</div>
  if (!data) return <div className="panel loading">Считаем итоги…</div>

  const money = data.table.chip_value > 0
  const sorted = [...data.players].sort((a, b) => b.net_chips - a.net_chips)
  const nameOf = (id: number) =>
    data.players.find((p) => p.user_id === id)?.name ?? `Игрок ${id}`

  const shareText = [
    `🏁 «${data.table.name}» — итоги`,
    `Раздач: ${data.hands_played}${data.table.duration ? ` · ${data.table.duration}` : ''}`,
    '',
    ...sorted.map((p) => `${p.name}: ${money ? signedCents(p.net_cents) : signedChips(p.net_chips)}`),
    ...(data.transfers.length
      ? ['', 'Расчёты:', ...data.transfers.map((t) => `${nameOf(t.from_user_id)} → ${nameOf(t.to_user_id)} ${formatCents(t.cents)}`)]
      : []),
  ].join('\n')

  const share = () => {
    const url =
      'https://t.me/share/url' +
      `?url=${encodeURIComponent(window.location.origin)}` +
      `&text=${encodeURIComponent(shareText)}`
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(url)
      return
    }
    void navigator.clipboard
      ?.writeText(shareText)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 2000)
      })
      .catch(() => undefined)
  }

  return (
    <section className="panel">
      <h2 className="section-title">🏁 Итоги сессии</h2>
      <div className="settle-meta">
        Раздач: {data.hands_played}
        {data.table.duration ? ` · ${data.table.duration}` : ''}
        {money ? ` · фишка ${formatCents(Math.round(data.table.chip_value * 100))}` : ' · играли просто так'}
      </div>

      <div className="settle-rows">
        {sorted.map((p) => (
          <div key={p.user_id} className="settle-row">
            <span className="settle-name">{p.name}</span>
            <span className="settle-bought">вложил {p.bought}</span>
            <span
              className={`settle-net ${
                p.net_chips > 0 ? 'net-plus' : p.net_chips < 0 ? 'net-minus' : ''
              }`}
            >
              {money ? signedCents(p.net_cents) : signedChips(p.net_chips)}
            </span>
          </div>
        ))}
      </div>

      {data.transfers.length > 0 && (
        <div className="transfers">
          <h3 className="section-title">💸 Кто кому сколько</h3>
          {data.transfers.map((t, i) => (
            <div key={i} className="transfer-row">
              {nameOf(t.from_user_id)} → {nameOf(t.to_user_id)}{' '}
              <b>{formatCents(t.cents)}</b>
            </div>
          ))}
        </div>
      )}

      <button className="btn-secondary" onClick={share}>
        {copied ? '✓ Скопировано' : '📨 Поделиться итогами'}
      </button>
    </section>
  )
}
