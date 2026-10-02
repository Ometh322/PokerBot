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
  you: { seat: number | null; is_host: boolean }
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
