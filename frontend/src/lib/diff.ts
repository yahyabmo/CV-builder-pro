export interface Piece {
  text: string
  kind: 'same' | 'added' | 'removed'
}

// Mots (avec « C++ », « Node.js », « A* »), espaces et ponctuation séparés.
const TOKEN = /\s+|[\p{L}\p{N}_+#.*/'’-]+|[^\s\p{L}\p{N}]/gu

/** Différence mot à mot entre deux textes courts (plus longue sous-suite commune). */
export function wordDiff(before: string, after: string): Piece[] {
  const a = before.match(TOKEN) ?? []
  const b = after.match(TOKEN) ?? []
  const n = a.length
  const m = b.length
  const table = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
  const raw: Piece[] = []
  const push = (text: string, kind: Piece['kind']) => {
    const last = raw.at(-1)
    if (last && last.kind === kind) last.text += text
    else raw.push({ text, kind })
  }
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      push(a[i], 'same')
      i++
      j++
    } else if (table[i + 1][j] >= table[i][j + 1]) push(a[i++], 'removed')
    else push(b[j++], 'added')
  }
  while (i < n) push(a[i++], 'removed')
  while (j < m) push(b[j++], 'added')
  return grouped(raw)
}

// « [-Conception-][+Design+] [-et-][+and+] » devient « [-Conception et-][+Design and+] » :
// un espace seul entre deux changements est absorbé, l'ancien texte puis le nouveau.
function grouped(pieces: Piece[]): Piece[] {
  const out: Piece[] = []
  let removed = ''
  let added = ''
  const flush = () => {
    if (removed) out.push({ text: removed, kind: 'removed' })
    if (added) out.push({ text: added, kind: 'added' })
    removed = ''
    added = ''
  }
  pieces.forEach((piece, k) => {
    const next = pieces[k + 1]
    if (piece.kind === 'removed') removed += piece.text
    else if (piece.kind === 'added') added += piece.text
    else if (/^\s+$/.test(piece.text) && (removed || added) && next && next.kind !== 'same') {
      removed += removed ? piece.text : ''
      added += added ? piece.text : ''
    } else {
      flush()
      out.push(piece)
    }
  })
  flush()
  return out
}
