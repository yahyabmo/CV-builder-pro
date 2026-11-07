import { Loader2, Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { AutoTextarea } from '@/components/editor/fields'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import type { RuleKind } from '@/lib/types'

interface RulesEditorProps {
  kind: RuleKind
  title: string
  description: React.ReactNode
  addLabel?: string
  placeholder?: string
}

/** Une liste de règles : un champ par règle, supprimable, et un bouton pour en ajouter. */
export function RulesEditor({ kind, title, description, addLabel = 'Ajouter une règle', placeholder }: RulesEditorProps) {
  const [saved, setSaved] = useState<string[] | null>(null)
  const [rules, setRules] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const focusLast = useRef(false)
  const list = useRef<HTMLOListElement>(null)

  useEffect(() => {
    api.rules(kind).then(
      (loaded) => {
        setSaved(loaded.rules)
        setRules(loaded.rules)
      },
      () => setSaved([]),
    )
  }, [kind])

  // Une règle ajoutée reçoit la saisie tout de suite.
  useEffect(() => {
    if (!focusLast.current) return
    focusLast.current = false
    list.current?.querySelector<HTMLTextAreaElement>('li:last-child textarea')?.focus()
  }, [rules])

  const cleaned = rules.map((rule) => rule.trim()).filter(Boolean)
  const dirty = saved !== null && JSON.stringify(cleaned) !== JSON.stringify(saved)

  const save = async () => {
    setSaving(true)
    try {
      const result = await api.saveRules(kind, cleaned)
      setSaved(result.rules)
      // Une retouche faite pendant l'enregistrement reste à l'écran.
      setRules((current) => (JSON.stringify(current) === JSON.stringify(rules) ? result.rules : current))
      toast.success('Règles enregistrées')
    } catch (error) {
      toast.error('Enregistrement impossible', { description: (error as Error).message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="flex flex-col gap-2" aria-label={title}>
      <h2 className="text-[13px] font-semibold">{title}</h2>
      <p className="text-[12px] text-muted-foreground">{description}</p>
      {saved === null ? (
        <Skeleton className="h-32 w-full rounded-lg" />
      ) : (
        <ol ref={list} className="flex flex-col gap-1.5">
          {rules.map((rule, i) => (
            <li key={i} className="group/rule flex items-start gap-1.5">
              <span className="mt-2 w-5 shrink-0 text-right text-[11px] text-muted-foreground tabular-nums">{i + 1}.</span>
              <AutoTextarea
                value={rule}
                placeholder={placeholder}
                onChange={(e) => setRules(rules.map((r, j) => (j === i ? e.target.value : r)))}
                aria-label={`${title} : règle ${i + 1}`}
              />
              <Button
                variant="ghost"
                size="icon"
                className="size-8 shrink-0 text-muted-foreground hover:text-destructive"
                aria-label={`Supprimer la règle ${i + 1}`}
                onClick={() => setRules(rules.filter((_, j) => j !== i))}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </li>
          ))}
        </ol>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-1.5 text-[12px]"
          onClick={() => {
            focusLast.current = true
            setRules([...rules, ''])
          }}
        >
          <Plus className="size-3.5" /> {addLabel}
        </Button>
        <Button size="sm" className="h-8 gap-1.5 text-[12px]" disabled={!dirty || saving} onClick={() => void save()}>
          {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />} Enregistrer
        </Button>
        {dirty && <span className="text-[11.5px] text-muted-foreground">Modifications non enregistrées</span>}
      </div>
    </section>
  )
}
