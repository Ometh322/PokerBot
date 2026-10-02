import { useCallback, useEffect, useState } from 'react'
import { fetchTables, type AuthResponse } from '../api'
import { statusLabel } from '../ui'
import type { TableSummary } from '../types'

interface Props {
  auth: AuthResponse
  onOpenTable: (code: string) => void
  onCreate: () => void
}

export default function Home({ auth, onOpenTable, onCreate }: Props) {
  const [tables, setTables] = useState<TableSummary[] | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    fetchTables(auth.token)
      .then(setTables)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [auth.token])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 20000)
    return () => window.clearInterval(timer)
  }, [load])

  return (
    <div className="app">
      <header className="header">
        <div className="logo">🃏</div>
        <div>
          <h1>Покер-клуб</h1>
          <p className="subtitle">Холдем с друзьями на условные фишки</p>
        </div>
      </header>

      {error && <div className="panel error-banner">{error}</div>}

      {tables === null ? (
        <div className="panel loading">Загружаем твои столы…</div>
      ) : tables.length === 0 ? (
        <div className="panel empty-state">
          <span className="suits">♠ ♥ ♦ ♣</span>
          <p>Активных столов пока нет</p>
        </div>
      ) : (
        <div className="table-list">
          {tables.map((t) => (
            <button key={t.code} className="table-card" onClick={() => onOpenTable(t.code)}>
              <div className="table-card-body">
                <div className="tname">{t.name}</div>
                <div className="tmeta">
                  {statusLabel(t.status)} · игроков {t.players_count}/{t.max_seats}
                  {t.is_host ? ' · 👑 ты хост' : t.my_seat !== null ? ` · место #${t.my_seat + 1}` : ''}
                </div>
              </div>
              <span className="arrow">→</span>
            </button>
          ))}
        </div>
      )}

      <button className="btn-primary" onClick={onCreate}>
        🎲 Создать стол
      </button>
      <footer className="footer">Фаза M2 · лобби · v0.2</footer>
    </div>
  )
}
