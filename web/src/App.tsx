import { useEffect, useState } from 'react'
import { authenticate, type AuthResponse } from './api'
import './App.css'

type Phase = 'loading' | 'dev' | 'ready' | 'error'

const tg = window.Telegram?.WebApp

export default function App() {
  const [phase, setPhase] = useState<Phase>('loading')
  const [auth, setAuth] = useState<AuthResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    tg?.ready()
    tg?.expand()

    const initData = tg?.initData
    if (!initData) {
      // Открыто не в Telegram (например, vite dev в браузере).
      setPhase('dev')
      return
    }
    authenticate(initData)
      .then((res) => {
        setAuth(res)
        setPhase('ready')
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e))
        setPhase('error')
      })
  }, [])

  const user = auth?.user

  return (
    <div className="app">
      <header className="header">
        <div className="logo">🃏</div>
        <div>
          <h1>Покер-клуб</h1>
          <p className="subtitle">Холдем с друзьями на условные фишки</p>
        </div>
      </header>

      {phase === 'loading' && <div className="panel loading">Загружаем стол…</div>}

      {phase === 'dev' && (
        <div className="panel dev-banner">
          Открыто вне Telegram — авторизация недоступна. Открой клуб через кнопку
          в боте, чтобы играть по-настоящему.
        </div>
      )}

      {phase === 'error' && (
        <div className="panel error-banner">Не удалось авторизоваться: {error}</div>
      )}

      {(phase === 'ready' || phase === 'dev') && (
        <>
          {user && (
            <section className="panel user-card">
              {user.photo_url ? (
                <img className="avatar" src={user.photo_url} alt="" />
              ) : (
                <div className="avatar avatar-placeholder">
                  {user.first_name.slice(0, 1)}
                </div>
              )}
              <div className="user-meta">
                <div className="user-name">
                  {user.first_name} {user.last_name ?? ''}
                </div>
                <div className="user-id">id {user.id}</div>
              </div>
            </section>
          )}

          {auth?.start_param && (
            <section className="panel invite-card">
              <span className="chip">🎲 приглашение</span>
              <p>
                Ты открыл стол по ссылке <code>{auth.start_param}</code>. Посадка
                за стол появится в фазе M2.
              </p>
            </section>
          )}

          <section className="panel">
            <button className="btn-primary" disabled>
              🎲 Создать стол
            </button>
            <p className="hint">Создание столов появится в фазе M2</p>
            <div className="empty-state">
              <span className="suits">♠ ♥ ♦ ♣</span>
              <p>Активных столов пока нет</p>
            </div>
          </section>
        </>
      )}

      <footer className="footer">Фаза M1 · каркас · v0.1</footer>
    </div>
  )
}
