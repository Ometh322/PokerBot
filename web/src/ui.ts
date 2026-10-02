// Мелкие помощники отображения.

import type { TableStatus } from './types'

export function statusLabel(status: TableStatus): string {
  switch (status) {
    case 'lobby':
      return 'лобби'
    case 'active':
      return 'идёт игра'
    case 'finished':
      return 'завершён'
  }
}

export function chipLabel(value: number): string {
  return value > 0 ? `фишка ${formatMoney(value)} ₽` : 'играем просто так'
}

export function rebuyLabel(mode: string): string {
  switch (mode) {
    case 'off':
      return 'без ребая'
    case 'anytime':
      return 'ребай в любой момент'
    default:
      return 'ребай при 0'
  }
}

function formatMoney(value: number): string {
  return String(value).replace('.', ',')
}
