import { Download, ExternalLink, FileText } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { api } from '@/lib/api'
import { company, dayLabel, lateText, monogram, position, STATUS, STATUS_ORDER, where } from '@/lib/applications'
import type { ApplicationPatch, CVSummary, LetterState } from '@/lib/types'
import { cn } from '@/lib/utils'

interface ApplicationSheetProps {
  cv: CVSummary | null
  onClose: () => void
  onOpenCV: (slug: string) => void
  onSaved: (cv: CVSummary) => void
}

const field =
  'h-9 rounded-md border bg-background px-3 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40'

/** La fiche d'une candidature : statut, dates, contact, notes, historique. Tout s'enregistre seul. */
export function ApplicationSheet({ cv, onClose, onOpenCV, onSaved }: ApplicationSheetProps) {
  return (
    <Sheet open={cv !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent>{cv && <Fiche key={cv.slug} cv={cv} onOpenCV={onOpenCV} onSaved={onSaved} />}</SheetContent>
    </Sheet>
  )
}

function Fiche({ cv, onOpenCV, onSaved }: { cv: CVSummary; onOpenCV: (slug: string) => void; onSaved: (cv: CVSummary) => void }) {
  const app = cv.meta.application
  const [contact, setContact] = useState(app.contact)
  const [email, setEmail] = useState(app.contact_email)
  const [notes, setNotes] = useState(app.notes)
  const [url, setUrl] = useState(cv.meta.offer_url ?? '')
  const [letter, setLetter] = useState<LetterState | null>(null)
  const { letter: initial, tint } = monogram(cv)

  useEffect(() => {
    api.letter(cv.slug).then(setLetter, () => setLetter(null))
  }, [cv.slug])

  const save = async (patch: ApplicationPatch) => {
    try {
      onSaved(await api.updateApplication(cv.slug, patch))
    } catch (error) {
      toast.error('Enregistrement impossible', { description: error instanceof Error ? error.message : String(error) })
    }
  }
  // Un texte s'enregistre en quittant le champ, s'il a changé.
  const keep = (key: 'contact' | 'contact_email' | 'notes', value: string, before: string) => {
    if (value.trim() !== before) void save({ [key]: value })
  }

  const history = [
    ...app.history,
    ...(cv.meta.company ? [{ on: cv.meta.created_at, text: `CV ciblé créé${cv.meta.score != null ? `, ${cv.meta.score} %` : ''}` }] : []),
  ]

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-6 overflow-y-auto p-6 pr-14">
        <div className="flex items-start gap-3">
          <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-lg text-[15px] font-bold', tint)}>{initial}</span>
          <div className="flex min-w-0 flex-col gap-1">
            <SheetDescription>
              {company(cv)} · {where(cv)}
            </SheetDescription>
            <SheetTitle>{position(cv)}</SheetTitle>
          </div>
        </div>

        {cv.due && app.follow_up_on && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-status-interview/30 bg-status-interview-soft px-3 py-2.5 text-[12.5px] text-status-interview">
            <span className="flex-1 font-medium">{lateText(app.follow_up_on)}</span>
            <Button size="sm" variant="outline" className="h-7 bg-background text-[12px]" onClick={() => void save({ followed_up: true })}>
              Relancée aujourd'hui
            </Button>
          </div>
        )}

        <section className="flex flex-col gap-2">
          <h3 className="text-[11.5px] font-semibold tracking-wide text-muted-foreground uppercase">Statut</h3>
          <div role="radiogroup" aria-label="Statut de la candidature" className="grid grid-cols-5 gap-1 rounded-lg bg-muted p-1">
            {STATUS_ORDER.map((status) => {
              const active = app.status === status
              return (
                <button
                  key={status}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => !active && void save({ status })}
                  className={cn(
                    'h-8 rounded-md text-[12px] transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                    active ? cn('font-semibold shadow-xs', STATUS[status].pill) : 'text-foreground/80 hover:bg-background/70',
                  )}
                >
                  {STATUS[status].label}
                </button>
              )
            })}
          </div>
        </section>

        <section className="grid grid-cols-2 gap-x-3 gap-y-4">
          <label className="flex flex-col gap-1.5 text-[12px] font-medium">
            Envoyée le
            <input
              type="date"
              value={app.sent_on ?? ''}
              onChange={(e) => void save({ sent_on: e.target.value || null })}
              aria-label="Date d'envoi"
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-[12px] font-medium">
            Relance prévue
            <input
              type="date"
              value={app.follow_up_on ?? ''}
              onChange={(e) => void save({ follow_up_on: e.target.value || null })}
              aria-label="Date de relance"
              className={field}
            />
          </label>
          <p className="col-span-2 -mt-2 text-[11.5px] text-muted-foreground">Proposée dix jours après l'envoi, modifiable.</p>
          <label className="col-span-2 flex flex-col gap-1.5 text-[12px] font-medium">
            Lien de l'offre
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={() => url.trim() !== (cv.meta.offer_url ?? '') && void save({ offer_url: url })}
              placeholder="https://…"
              aria-label="Lien de l'offre"
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-[12px] font-medium">
            Contact
            <input
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              onBlur={() => keep('contact', contact, app.contact)}
              placeholder="Nom de la personne"
              aria-label="Contact"
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-[12px] font-medium">
            Email du contact
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => keep('contact_email', email, app.contact_email)}
              placeholder="prenom.nom@example.com"
              aria-label="Email du contact"
              className={field}
            />
          </label>
          <label className="col-span-2 flex flex-col gap-1.5 text-[12px] font-medium">
            Notes
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => keep('notes', notes, app.notes)}
              rows={3}
              placeholder="Ce qu'il faut retenir : un échange, une question à préparer…"
              aria-label="Notes"
              className="resize-y rounded-md border bg-background px-3 py-2 text-[13px] shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/40"
            />
          </label>
        </section>

        <section className="flex flex-col gap-2.5">
          <h3 className="text-[11.5px] font-semibold tracking-wide text-muted-foreground uppercase">Historique</h3>
          <ol aria-label="Historique" className="flex flex-col gap-2.5 border-l-2 pl-3.5">
            {history.map((event, i) => (
              <li key={`${event.on}-${i}`} className="flex gap-3 text-[13px]">
                <span className="w-14 shrink-0 pt-px font-mono text-[11.5px] text-muted-foreground tabular-nums">{dayLabel(event.on)}</span>
                <span>{event.text}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <div className="mt-auto flex flex-wrap gap-2 border-t p-4">
        <Button onClick={() => onOpenCV(cv.slug)} className="gap-1.5">
          <FileText className="size-4" /> Ouvrir le CV
        </Button>
        <Button variant="outline" asChild disabled={!cv.pdf_version}>
          <a href={api.pdfUrl(cv.slug, cv.pdf_version)} download={`${cv.file_stem}.pdf`}>
            <Download className="size-4" /> CV
          </a>
        </Button>
        {letter?.letter && letter.pdf_version && (
          <Button variant="outline" asChild>
            <a href={api.letterPdfUrl(cv.slug, letter.pdf_version)} download={`${letter.file_stem}.pdf`}>
              <Download className="size-4" /> Lettre
            </a>
          </Button>
        )}
        {cv.meta.offer_url && (
          <Button variant="ghost" asChild className="text-primary">
            <a href={cv.meta.offer_url} target="_blank" rel="noreferrer">
              <ExternalLink className="size-4" /> Voir l'offre
            </a>
          </Button>
        )}
      </div>
    </div>
  )
}
