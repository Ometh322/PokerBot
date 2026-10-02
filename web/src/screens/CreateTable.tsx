import { useState } from 'react'
import { createTable, type AuthResponse } from '../api'
import type { RebuyMode, TableSettings } from '../types'

interface Props {
  auth: AuthResponse
  onCreated: (code: string) => void
  onCancel: () => void
}

const STACK_PRESETS = ['500', '1000', '2000', 'custom']
const BLINDS_PRESETS = ['1/2', '5/10', '10/20', '25/50', 'custom']
const CHIP_PRESETS = [
  { value: '0', label: 'Просто так' },
  { value: '0.1', label: '0,1 ₽' },
  { value: '1', label: '1 ₽' },
  { value: '10', label: '10 ₽' },
  { value: 'custom', label: 'Своя…' },
]
const TIMEOUT_PRESETS = [
  { value: '30', label: '30 сек' },
  { value: '60', label: '60 сек' },
  { value: '90', label: '90 сек' },
  { value: 'none', label: 'Без лимита' },
]

function toPositiveInt(value: string): number {
  const n = Number(value)
  if (!Number.isInteger(n) || n <= 0) throw new Error('введи целое положительное число')
  return n
}

export default function CreateTable({ auth, onCreated, onCancel }: Props) {
  const [name, setName] = useState('')
  const [stackPreset, setStackPreset] = useState('1000')
  const [stackCustom, setStackCustom] = useState('1500')
  const [blindsPreset, setBlindsPreset] = useState('5/10')
  const [sbCustom, setSbCustom] = useState('3')
  const [bbCustom, setBbCustom] = useState('6')
  const [rebuy, setRebuy] = useState<RebuyMode>('busted')
  const [chipPreset, setChipPreset] = useState('1')
  const [chipCustom, setChipCustom] = useState('2')
  const [seats, setSeats] = useState('6')
  const [timeoutPreset, setTimeoutPreset] = useState('60')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const [sb, bb] =
        blindsPreset === 'custom' ? [sbCustom, bbCustom] : blindsPreset.split('/')
      const chipValue =
        chipPreset === 'custom' ? Number(chipCustom.replace(',', '.')) : Number(chipPreset)
      if (!Number.isFinite(chipValue) || chipValue < 0) {
        throw new Error('цена фишки: введи неотрицательное число')
      }
      const settings: TableSettings = {
        starting_stack: stackPreset === 'custom' ? toPositiveInt(stackCustom) : Number(stackPreset),
        small_blind: toPositiveInt(sb),
        big_blind: toPositiveInt(bb),
        rebuy_mode: rebuy,
        chip_value: chipValue,
        max_seats: Number(seats),
        action_timeout: timeoutPreset === 'none' ? null : Number(timeoutPreset),
      }
      const res = await createTable(auth.token, { name, settings })
      onCreated(res.code)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <div className="topbar">
        <button className="btn-ghost" onClick={onCancel}>
          ← Отмена
        </button>
      </div>

      <section className="panel">
        <h2 className="section-title">🎲 Новый стол</h2>

        <div className="form-field">
          <label htmlFor="t-name">Название</label>
          <input
            id="t-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Пятница"
            maxLength={32}
          />
        </div>

        <div className="form-field">
          <label>Стартовый стек</label>
          <div className="preset-row">
            {STACK_PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                className={`preset ${stackPreset === p ? 'preset-active' : ''}`}
                onClick={() => setStackPreset(p)}
              >
                {p === 'custom' ? 'свой' : p}
              </button>
            ))}
          </div>
          {stackPreset === 'custom' && (
            <input
              inputMode="numeric"
              value={stackCustom}
              onChange={(e) => setStackCustom(e.target.value.replace(/\D/g, ''))}
            />
          )}
        </div>

        <div className="form-field">
          <label>Блайнды (SB/BB)</label>
          <div className="preset-row">
            {BLINDS_PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                className={`preset ${blindsPreset === p ? 'preset-active' : ''}`}
                onClick={() => setBlindsPreset(p)}
              >
                {p === 'custom' ? 'свои' : p}
              </button>
            ))}
          </div>
          {blindsPreset === 'custom' && (
            <div className="form-row">
              <input
                inputMode="numeric"
                value={sbCustom}
                onChange={(e) => setSbCustom(e.target.value.replace(/\D/g, ''))}
                placeholder="SB"
              />
              <input
                inputMode="numeric"
                value={bbCustom}
                onChange={(e) => setBbCustom(e.target.value.replace(/\D/g, ''))}
                placeholder="BB"
              />
            </div>
          )}
        </div>

        <div className="form-field">
          <label htmlFor="t-rebuy">Ребай (докупка стартового стека)</label>
          <select id="t-rebuy" value={rebuy} onChange={(e) => setRebuy(e.target.value as RebuyMode)}>
            <option value="off">Выключен</option>
            <option value="busted">При проигрыше всего стека</option>
            <option value="anytime">В любой момент</option>
          </select>
        </div>

        <div className="form-field">
          <label>Условная цена фишки</label>
          <div className="preset-row">
            {CHIP_PRESETS.map((p) => (
              <button
                key={p.value}
                type="button"
                className={`preset ${chipPreset === p.value ? 'preset-active' : ''}`}
                onClick={() => setChipPreset(p.value)}
              >
                {p.label}
              </button>
            ))}
          </div>
          {chipPreset === 'custom' && (
            <input
              inputMode="decimal"
              value={chipCustom}
              onChange={(e) => setChipCustom(e.target.value)}
              placeholder="2"
            />
          )}
        </div>

        <div className="form-row">
          <div className="form-field">
            <label htmlFor="t-seats">Мест за столом</label>
            <select id="t-seats" value={seats} onChange={(e) => setSeats(e.target.value)}>
              {[2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
                <option key={n} value={String(n)}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="t-timeout">Таймер хода</label>
            <select id="t-timeout" value={timeoutPreset} onChange={(e) => setTimeoutPreset(e.target.value)}>
              {TIMEOUT_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="panel error-banner">{error}</div>}

        <button className="btn-primary" disabled={busy} onClick={() => void submit()}>
          {busy ? 'Создаём…' : 'Создать стол'}
        </button>
      </section>
    </div>
  )
}
