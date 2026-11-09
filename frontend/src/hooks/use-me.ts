import { useEffect, useState } from 'react'

import { api } from '@/lib/api'
import type { Me } from '@/lib/types'

// Une seule lecture par chargement de page : la personne connectée ne change pas en route.
let asked: Promise<Me> | null = null

/** En ligne : l'e-mail de la personne connectée. En local : mode « local », sans e-mail. */
export function useMe(): Me | null {
  const [me, setMe] = useState<Me | null>(null)
  useEffect(() => {
    let live = true
    asked ??= api.me().catch(() => ({ mode: 'local', email: null }) as Me)
    void asked.then((found) => live && setMe(found))
    return () => {
      live = false
    }
  }, [])
  return me
}

/** L'adresse de déconnexion de Cloudflare Access, sur le même domaine que l'appli. */
export const LOGOUT_URL = '/cdn-cgi/access/logout'
