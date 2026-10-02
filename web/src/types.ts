// Общие типы, зеркалящие снапшоты бэкенда (PLAN.md, раздел 9).

export type RebuyMode = 'off' | 'busted' | 'anytime'

export interface TableSettings {
  starting_stack: number
  small_blind: number
  big_blind: number
  rebuy_mode: RebuyMode
  chip_value: number
  max_seats: number
  action_timeout: number | null
}

export type TableStatus = 'lobby' | 'active' | 'finished'

export interface PlayerInfo {
  user_id: number
  name: string
  photo_url: string | null
  seat: number
  stack: number
  status: string
  total_bought: number
  is_host: boolean
}

export interface LegalActions {
  fold: boolean
  check?: boolean
  call?: number
  raise_to?: [number, number]
}

export interface HandPlayerInfo {
  user_id: number
  stack: number
  bet: number
  folded: boolean
  all_in: boolean
}

export interface HandWinner {
  user_id: number
  amount: number
  hand: string | null
}

export interface HandResult {
  type: 'showdown' | 'uncontested'
  board: string[]
  pot_total: number
  pots: { amount: number; eligible: number[] }[]
  winners: HandWinner[]
}

export interface HandInfo {
  number: number
  street: 'preflop' | 'flop' | 'turn' | 'river' | 'showdown' | 'finished' | null
  board: string[]
  pot: number
  current_bet: number
  dealer_seat: number | null
  players: HandPlayerInfo[]
  to_act: number | null
  deadline: number | null
  next_hand_at: number | null
  waiting: boolean
  revealed: Record<string, string[]>
  last_result: HandResult | null
}

export interface YouInfo {
  seat: number | null
  is_host: boolean
  cards?: string[] | null
  legal_actions?: LegalActions | null
}

export interface Snapshot {
  code: string
  name: string
  status: TableStatus
  settings: TableSettings
  host_user_id: number
  invite_link: string
  seats_total: number
  created_at: string | null
  players: PlayerInfo[]
  you: YouInfo
  hand?: HandInfo | null
}

export interface TableSummary {
  code: string
  name: string
  status: TableStatus
  players_count: number
  max_seats: number
  my_seat: number | null
  is_host: boolean
}
