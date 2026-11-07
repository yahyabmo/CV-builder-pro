import { Check, CircleAlert, Eye, EyeOff, Loader2, Lock } from 'lucide-react'
import { useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { KEY_NAMES, SECRET_LABELS, SECRET_PLACEHOLDERS } from '@/lib/keys'
import type { KeyProvider, KeyResult } from '@/lib/types'
import { cn } from '@/lib/utils'

const seconds = (s: number) => `${String(s).replace('.', ',')} s`

interface KeyFormProps {
  provider: KeyProvider
  /** La clé est acceptée et enregistrée dans .env. */
  onSaved: (result: KeyResult) => void
  /** Réglages : champ plus petit, sans la mention sur .env (elle est en bas de la section). */
  compact?: boolean
}

/**
 * Le champ d'une clé d'API : masqué, avec « Vérifier ». Le serveur essaie la clé par
 * un petit appel et ne l'écrit dans .env que si le fournisseur l'accepte. Le champ se
 * vide ensuite : la clé ne reste pas dans la page.
 */
export function KeyForm({ provider, onSaved, compact }: KeyFormProps) {
  const id = useId()
  const [key, setKey] = useState('')
  const [shown, setShown] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<KeyResult | null>(null)
  const [problem, setProblem] = useState('')
  const name = KEY_NAMES[provider]
  // Le relais de Yahya demande un code d'accès, pas une clé d'API.
  const code = provider === 'relais'

  const verify = async () => {
    setResult(null)
    if (!key.trim()) {
      setProblem(code ? "Colle d'abord ton code d'accès dans le champ." : "Colle d'abord ta clé dans le champ.")
      return
    }
    setProblem('')
    setBusy(true)
    try {
      const answer = await api.saveKey(provider, key)
      setResult(answer)
      if (answer.saved) {
        setKey('')
        onSaved(answer)
      }
    } catch (error) {
      setProblem((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-col gap-1.5">
        <label htmlFor={id} className={cn('font-medium', compact ? 'text-[12px]' : 'text-[12.5px]')}>
          {SECRET_LABELS[provider]}
        </label>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            void verify()
          }}
        >
          <div
            className={cn(
              'flex min-w-0 flex-[1_1_260px] items-center rounded-lg border bg-card focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/30',
              result && !result.ok && 'border-destructive/60',
            )}
          >
            <input
              id={id}
              type={shown ? 'text' : 'password'}
              value={key}
              onChange={(event) => {
                setKey(event.target.value)
                setProblem('')
                setResult(null)
              }}
              placeholder={SECRET_PLACEHOLDERS[provider]}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={result != null && !result.ok}
              className={cn('min-w-0 flex-1 bg-transparent px-3 font-mono text-[13px] outline-none', compact ? 'h-8' : 'h-10')}
            />
            <button
              type="button"
              onClick={() => setShown(!shown)}
              aria-label={shown ? (code ? 'Masquer le code' : 'Masquer la clé') : code ? 'Afficher le code' : 'Afficher la clé'}
              className={cn('flex items-center justify-center text-muted-foreground hover:text-foreground', compact ? 'size-8' : 'size-10')}
            >
              {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          <Button
            type="submit"
            variant={compact ? 'default' : 'outline'}
            disabled={busy}
            className={cn('gap-1.5', compact ? 'h-8' : 'h-10.5 border-primary/35 bg-accent px-4.5 font-semibold text-accent-foreground hover:bg-accent/70')}
          >
            {busy && <Loader2 className="size-4 animate-spin" />}
            {busy ? 'Vérification…' : compact ? 'Vérifier et enregistrer' : 'Vérifier'}
          </Button>
        </form>
      </div>

      {busy && <p className="text-[12.5px] text-muted-foreground">{code ? 'Vérification du code auprès du relais de Yahya…' : `Une petite requête de test à ${name}…`}</p>}
      {problem && <p className="text-[12.5px] text-warning">{problem}</p>}
      {result?.ok && (
        <p role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-status-offer-soft px-2.5 py-1 font-semibold text-status-offer">
            <Check className="size-3.5" /> {code ? 'Code valide' : 'Clé valide'}
          </span>
          <span className="text-muted-foreground">
            {result.message || `${result.model} a répondu en ${seconds(result.seconds)} · enregistrée dans .env`}
          </span>
        </p>
      )}
      {result && !result.ok && (
        <div role="alert" className="flex items-start gap-2.5 rounded-lg bg-destructive/8 px-3.5 py-3 text-[13px] leading-relaxed text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{result.message}</span>
        </div>
      )}
      {!compact && !busy && !result && !problem && (
        <p className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <Lock className="size-3.5 shrink-0" />
          {code
            ? "Enregistré dans le fichier .env de ce dossier, sur ta machine. L'appli ne le renvoie jamais, pas même à l'écran."
            : "Enregistrée dans le fichier .env de ce dossier, sur ta machine. L'appli ne la renvoie jamais, pas même à l'écran."}
        </p>
      )}
    </div>
  )
}
