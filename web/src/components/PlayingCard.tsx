// Игральная карта: код 'As' → плашка с рангом и мастью.
// flip — анимация переворота (борд, вскрытие); по умолчанию — выдача сверху.

const SUIT_SYMBOL: Record<string, string> = { s: '♠', h: '♥', d: '♦', c: '♣' }

export default function PlayingCard({
  code,
  small,
  flip,
}: {
  code: string
  small?: boolean
  flip?: boolean
}) {
  const rank = code[0] === 'T' ? '10' : code[0]
  const suit = code[1]
  const red = suit === 'h' || suit === 'd'
  const cls = [
    'pcard',
    small ? 'pcard-sm' : '',
    red ? 'pcard-red' : '',
    flip ? 'pcard-flip' : '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <div className={cls}>
      <span className="pcard-rank">{rank}</span>
      <span className="pcard-suit">{SUIT_SYMBOL[suit] ?? '?'}</span>
    </div>
  )
}
