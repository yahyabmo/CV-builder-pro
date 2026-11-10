import { LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { LOGOUT_URL } from '@/hooks/use-me'
import { api } from '@/lib/api'
import type { OnlineAI, Provider } from '@/lib/types'
import { cn } from '@/lib/utils'

/** Le reste du jour de l'IA en ligne, en une phrase. */
function quotaLine(online: OnlineAI | null | undefined): string {
  if (!online) return ''
  if (!online.ok) return 'IA indisponible pour le moment'
  if (online.exhausted) return 'IA : crédit du mois épuisé'
  if (online.left == null) return ''
  if (online.left === 0) return 'IA : plus de demandes aujourd’hui'
  return `IA : ${online.left} demande${online.left > 1 ? 's' : ''} restante${online.left > 1 ? 's' : ''} aujourd’hui`
}

/** En ligne, en bas du menu : qui est connecté, son reste d'IA du jour, la déconnexion. */
interface AccountProps {
  email: string
  collapsed: boolean
  refreshKey: string
  openPrivacy: () => void
}

export function Account({ email, collapsed, refreshKey, openPrivacy }: AccountProps) {
  const [online, setOnline] = useState<OnlineAI | null>(null)
  const [provider, setProvider] = useState<Provider>('relais')

  // Relu à chaque changement de page : un ciblage vient peut-être d'utiliser des demandes.
  useEffect(() => {
    let live = true
    api.getSettings().then(
      (info) => {
        if (!live) return
        setOnline(info.online ?? null)
        setProvider(info.ai.provider)
      },
      () => undefined,
    )
    return () => {
      live = false
    }
  }, [refreshKey])

  const initial = email.charAt(0).toUpperCase()
  // Avec sa propre clé, le quota du relais ne la concerne pas.
  const quota = provider === 'gemini' ? 'IA : ta clé Gemini' : provider === 'mistral' ? 'IA : ta clé Mistral' : quotaLine(online)

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <a
            href={LOGOUT_URL}
            aria-label={`Connecté : ${email}. Se déconnecter`}
            className="flex size-8 items-center justify-center rounded-full bg-primary/80 text-[12px] font-bold text-primary-foreground"
          >
            {initial}
          </a>
        </TooltipTrigger>
        <TooltipContent side="right">
          {email}
          {quota && ` · ${quota}`} · cliquer pour se déconnecter
        </TooltipContent>
      </Tooltip>
    )
  }

  return (
    <div className="flex w-full flex-col gap-2 rounded-xl border bg-background/70 p-2.5">
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/80 text-[12.5px] font-bold text-primary-foreground"
        >
          {initial}
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="text-[12.5px] font-semibold">Connecté</span>
          <span className="truncate text-[11.5px] text-muted-foreground" title={email}>
            {email}
          </span>
        </span>
      </div>
      {quota && (
        <p role="status" className={cn('text-[11.5px] text-muted-foreground', online?.left === 0 && 'text-warning')}>
          {quota}
        </p>
      )}
      <a
        href={LOGOUT_URL}
        className="flex h-8 items-center justify-center gap-1.5 rounded-lg border text-[12.5px] font-semibold transition-colors hover:bg-sidebar-accent"
      >
        <LogOut className="size-3.5" /> Se déconnecter
      </a>
      <button type="button" onClick={openPrivacy} className="self-start text-[11.5px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
        Confidentialité de tes données
      </button>
    </div>
  )
}
