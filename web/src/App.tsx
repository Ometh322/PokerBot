import { useEffect, useState, type ReactNode } from 'react'
import { authenticate, devAuth, type AuthResponse } from './api'
import Home from './screens/Home'
import CreateTable from './screens/CreateTable'
import TableScreen from './screens/TableScreen'
import './App.css'

type Phase = 'loading' | 'need-login' | 'ready' | 'error'
type View = { kind: 'home' } | { kind: 'create' } | { kind: 'table'; code: string }

const tg = window.Telegram?.WebApp

// Приглашение приходит одним из способов:
// - initData.start_param (зарегистрированное в BotFather Mini App);
// - ?table=<код> — кнопка бота из deep-link-приглашения;
// - #tbl_<код> — старый фолбэк.
function viewFromStartParam(startParam?: string | null): View | null {
  if (startParam && startParam.startsWith('tbl_')) {
    return { kind: 'table', code: startParam.slice(4) }
  }
  const query = new URLSearchParams(window.location.search).get('table')
  if (query) return { kind: 'table', code: query.replace(/^tbl_/, '') }
  const hash = window.location.hash.replace(/^#/, '')
  if (hash.startsWith('tbl_')) return { kind: 'table', code: hash.slice(4) }
  return null
}

export default function App() {
  const [phase, setPhase] = useState<Phase>('loading')
  const [auth, setAuth] = useState<AuthResponse | null>(null)
  const [error, setError] = useState('')
  const [view, setView] = useState<View>({ kind: 'home' })

  useEffect(() => {
    tg?.ready()
    tg?.expand()

    const initData = tg?.initData
    if (!initData) {
      // Открыто не в Telegram (например, vite dev в браузере).
      setPhase('need-login')
      return
    }
    authenticate(initData)
      .then((res) => {
        setAuth(res)
        setPhase('ready')
        const initial = viewFromStartParam(res.start_param)
        if (initial) setView(initial)
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e))
        setPhase('error')
      })
  }, [])

  if (phase === 'loading') {
    return (
      <Shell>
        <div className="panel loading">Загружаем клуб…</div>
      </Shell>
    )
  }
  if (phase === 'error') {
    return (
      <Shell>
        <div className="panel error-banner">Не удалось авторизоваться: {error}</div>
      </Shell>
    )
  }
  if (phase === 'need-login') {
    return (
      <Shell>
        <DevLogin onAuth={(res) => { setAuth(res); setPhase('ready') }} />
        <div className="panel dev-banner">
          Открыто вне Telegram. Чтобы войти тестовым игроком, включи на сервере{' '}
          <code>DEV_MODE=1</code>; либо открой клуб кнопкой в боте.
        </div>
      </Shell>
    )
  }
  if (auth === null) return null

  switch (view.kind) {
    case 'create':
      return (
        <CreateTable
          auth={auth}
          onCreated={(code) => setView({ kind: 'table', code })}
          onCancel={() => setView({ kind: 'home' })}
        />
      )
    case 'table':
      return (
        <TableScreen
          code={view.code}
          auth={auth}
          onExit={() => setView({ kind: 'home' })}
        />
      )
    default:
      return (
        <Home
          auth={auth}
          onOpenTable={(code) => setView({ kind: 'table', code })}
          onCreate={() => setView({ kind: 'create' })}
        />
      )
  }
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="app">
      <header className="header">
        <div className="logo">🃏</div>
        <div>
          <h1>Покер-клуб</h1>
          <p className="subtitle">Холдем с друзьями на условные фишки</p>
        </div>
      </header>
      {children}
    </div>
  )
}

function DevLogin({ onAuth }: { onAuth: (auth: AuthResponse) => void }) {
  const [userId, setUserId] = useState(
    () =>
      window.localStorage.getItem('pb_dev_id') ??
      String(100000 + Math.floor(Math.random() * 899999)),
  )
  const [name, setName] = useState(() => window.localStorage.getItem('pb_dev_name') ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const login = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await devAuth(Number(userId), name.trim() || `Гость ${userId.slice(-3)}`)
      window.localStorage.setItem('pb_dev_id', userId)
      window.localStorage.setItem('pb_dev_name', name)
      onAuth(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2 className="section-title">Дев-вход</h2>
      <div className="form-field">
        <label htmlFor="dev-id">Telegram ID</label>
        <input
          id="dev-id"
          inputMode="numeric"
          value={userId}
          onChange={(e) => setUserId(e.target.value.replace(/\D/g, ''))}
        />
      </div>
      <div className="form-field">
        <label htmlFor="dev-name">Имя</label>
        <input
          id="dev-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Аня"
        />
      </div>
      {error && <div className="panel error-banner">{error}</div>}
      <button className="btn-primary" disabled={busy || userId === ''} onClick={() => void login()}>
        Войти
      </button>
      <p className="hint">Разные ID = разные игроки: открой пару окон браузера.</p>
    </section>
  )
}
