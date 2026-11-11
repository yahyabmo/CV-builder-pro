import { Loader2, Lock } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { LOGOUT_URL } from '@/hooks/use-me'

/** En ligne : l'administrateur a retiré l'accès de cette adresse. Rien d'autre ne s'affiche. */
export function AccessPaused({ email }: { email: string }) {
  const [busy, setBusy] = useState(false)

  const retry = async () => {
    setBusy(true)
    try {
      // Appel direct : api.* ne répond plus tant que l'accès est en pause.
      const answer = await fetch('/api/me')
      // L'accès est rendu : on repart d'une page neuve, avec toutes les données.
      if (answer.ok) return window.location.reload()
      setBusy(false)
      if (answer.status === 403) toast.info("L'accès n'est pas encore rendu.")
      else toast.error('Impossible de vérifier', { description: `Réponse ${answer.status} du serveur.` })
    } catch {
      setBusy(false)
      toast.error('Le serveur ne répond pas.')
    }
  }

  return (
    <main className="flex h-dvh items-center justify-center bg-background p-6">
      <div className="surface flex w-full max-w-md flex-col gap-3 rounded-2xl border bg-card p-7">
        <span className="flex size-10 items-center justify-center rounded-xl bg-warning/15 text-warning">
          <Lock className="size-5" />
        </span>
        <h1 className="text-[19px] font-semibold tracking-tight">Ton accès est en pause</h1>
        {email && (
          <>
            <p className="text-[13.5px] text-muted-foreground">Tu es connecté avec cette adresse :</p>
            <p className="rounded-lg bg-muted px-2.5 py-1.5 font-mono text-[12.5px] break-all">{email}</p>
          </>
        )}
        <p className="text-[13.5px] text-muted-foreground">
          Yahya a retiré l'accès de cette adresse. S'il te le redonne, clique sur « Réessayer ». Tes données ne sont pas touchées.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button onClick={() => void retry()} disabled={busy} className="gap-1.5">
            {busy && <Loader2 className="size-4 animate-spin" />} Réessayer
          </Button>
          <Button variant="outline" asChild>
            <a href={LOGOUT_URL}>Changer d'adresse</a>
          </Button>
        </div>
      </div>
    </main>
  )
}
