// Игральная карта: код 'As' → плашка с рангом и мастью.

const SUIT_SYMBOL: Record<string, string> = { s: '♠', h: '♥', d: '♦', c: '♣' }

export default function PlayingCard({ code, small }: { code: string; small?: boolean }) {
  const rank = code[0] === 'T' ? '10' : code[0]
  const suit = code[1]
  const red = suit === 'h' || suit === 'd'
  return (
    <div className={`pcard ${small ? 'pcard-sm' : ''} ${red ? 'pcard-red' : ''}`}>
      <span className="pcard-rank">{rank}</span>
      <span className="pcard-suit">{SUIT_SYMBOL[suit] ?? '?'}</span>
    </div>
  )
}
