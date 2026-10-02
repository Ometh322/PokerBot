// Лёгкие синтезированные звуки (WebAudio, без ассетов).
// По умолчанию выключены — переключаются кнопкой 🔊 за столом.

let ctx: AudioContext | null = null
let enabled = window.localStorage.getItem('pb_sound') === '1'

export function soundEnabled(): boolean {
  return enabled
}

export function toggleSound(): boolean {
  enabled = !enabled
  window.localStorage.setItem('pb_sound', enabled ? '1' : '0')
  return enabled
}

function beep(freq: number, duration: number, delay: number, volume = 0.05): void {
  if (!enabled) return
  try {
    ctx ??= new AudioContext()
    if (ctx.state === 'suspended') void ctx.resume()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = freq
    const at = ctx.currentTime + delay
    gain.gain.setValueAtTime(volume, at)
    gain.gain.exponentialRampToValueAtTime(0.0001, at + duration)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(at)
    osc.stop(at + duration)
  } catch {
    // звук — косметика, ошибки глотаем
  }
}

export function playDeal(): void {
  beep(660, 0.07, 0)
  beep(880, 0.06, 0.08)
}

export function playTurn(): void {
  beep(520, 0.09, 0)
}

export function playWin(): void {
  beep(523, 0.12, 0)
  beep(659, 0.12, 0.1)
  beep(784, 0.18, 0.2)
}
