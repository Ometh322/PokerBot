// Минимальные типы Telegram WebApp SDK (script из index.html).
// Полный контракт: https://core.telegram.org/bots/webapps

export interface TelegramWebAppUser {
  id: number
  first_name: string
  last_name?: string
  username?: string
  photo_url?: string
  is_premium?: boolean
}

export interface TelegramWebApp {
  initData: string
  initDataUnsafe: { start_param?: string; user?: TelegramWebAppUser }
  version: string
  platform: string
  colorScheme: 'light' | 'dark'
  themeParams: Record<string, string>
  isExpanded: boolean
  ready(): void
  expand(): void
  close(): void
  openTelegramLink(url: string): void
  openLink?(url: string, options?: { try_instant_view?: boolean }): void
  setHeaderColor?(color: string): void
  setBackgroundColor?(color: string): void
  onEvent(event: string, callback: () => void): void
  offEvent(event: string, callback: () => void): void
  HapticFeedback?: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void
    notificationOccurred(type: 'error' | 'success' | 'warning'): void
    selectionChanged(): void
  }
}

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp }
  }
}
