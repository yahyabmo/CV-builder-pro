import { useCallback, useEffect, useState } from 'react'

import { api } from '@/lib/api'
import type { Machine } from '@/lib/types'

/** La machine vue par le serveur : relue au montage et à chaque « Vérifier à nouveau ». */
export function useMachine() {
  const [machine, setMachine] = useState<Machine | null>(null)
  const [busy, setBusy] = useState(true)
  const [failed, setFailed] = useState('')
  const refresh = useCallback(async () => {
    setBusy(true)
    try {
      setMachine(await api.checkMachine())
      setFailed('')
    } catch (error) {
      setFailed((error as Error).message)
    } finally {
      setBusy(false)
    }
  }, [])
  useEffect(() => {
    // Lecture au montage : l'état passe par refresh(), pas par l'effet lui-même.
    const frame = requestAnimationFrame(() => void refresh())
    return () => cancelAnimationFrame(frame)
  }, [refresh])
  return { machine, busy, failed, refresh }
}
