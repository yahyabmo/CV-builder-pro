import { useEffect, useState } from 'react'

import { api } from '@/lib/api'
import type { FontInfo } from '@/lib/types'

// La liste ne change pas pendant une session : un seul chargement, partagé.
let cache: Promise<FontInfo[]> | null = null

function load(): Promise<FontInfo[]> {
  cache ??= api.listFonts().then((list) => {
    // Chaque police est déclarée au navigateur (« CVB <id> ») pour que son nom
    // s'affiche dans sa propre police dans les menus.
    for (const font of list) {
      const face = new FontFace(`CVB ${font.id}`, `url(${api.fontUrl(font.id)})`)
      document.fonts.add(face)
      void face.load().catch(() => undefined)
    }
    return list
  })
  return cache
}

export function useFonts(): FontInfo[] {
  const [fonts, setFonts] = useState<FontInfo[]>([])
  useEffect(() => {
    let alive = true
    load()
      .then((list) => alive && setFonts(list))
      .catch(() => {
        cache = null
      })
    return () => {
      alive = false
    }
  }, [])
  return fonts
}
