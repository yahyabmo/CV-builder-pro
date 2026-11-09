import { ArrowLeft, Download } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { api } from '@/lib/api'

/** En ligne : ce que l'appli garde, où, et comment tout récupérer ou tout effacer. */
export function PrivacyPage() {
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b px-5">
        <a href="#/cvs" aria-label="Retour" className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" />
        </a>
        <h1 className="text-[13px] font-semibold tracking-tight">Confidentialité de tes données</h1>
      </header>
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-7">
          <p className="text-[13.5px] text-muted-foreground">Ce que CV Builder Pro garde, où, et comment tout effacer.</p>

          <Card title="Ce qui est gardé">
            <li>Ton adresse e-mail, pour te reconnaître à la connexion.</li>
            <li>Ta bibliothèque (expériences, projets, compétences), tes CV, tes lettres, tes thèmes et tes candidatures.</li>
            <li>Un compteur de demandes à l'IA par jour, sans le contenu des demandes.</li>
          </Card>

          <Card title="Où">
            <li>
              Sur un serveur en Europe (Allemagne), dans un dossier à ton nom. Les autres utilisateurs ne le voient jamais ; Yahya, qui gère
              le service, peut consulter tes CV et tes candidatures, sans les modifier.
            </li>
            <li>Tes données restent tant que ton compte existe, sans limite de durée.</li>
            <li>En plus, une copie de secours est faite chaque nuit ; les 7 plus récentes sont gardées pour réparer une panne.</li>
            <li>
              Quand tu utilises l'IA, le texte de l'offre et de ta bibliothèque passe par Google Gemini le temps de la réponse. Le relais
              de Yahya ne garde ni le texte ni ton adresse : seulement un compteur, sous une empreinte de ton e-mail.
            </li>
          </Card>

          <section className="flex flex-col gap-3 rounded-xl border bg-card surface p-5">
            <h2 className="text-[14.5px] font-semibold">Tout récupérer ou tout effacer</h2>
            <p className="text-[13px] leading-relaxed text-foreground/85">
              « Tout télécharger » te donne un zip de tout ce qui est à toi. Pour effacer ton compte, demande-le à Yahya : tes dossiers
              sont effacés tout de suite, et disparaissent des copies de secours au plus tard 7 jours après.
            </p>
            <Button asChild variant="outline" size="sm" className="gap-1.5 self-start">
              <a href={api.exportUrl} download>
                <Download className="size-3.5" /> Tout télécharger
              </a>
            </Button>
          </section>
        </div>
      </ScrollArea>
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2 rounded-xl border bg-card surface p-5">
      <h2 className="text-[14.5px] font-semibold">{title}</h2>
      <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[13px] leading-relaxed text-foreground/85">{children}</ul>
    </section>
  )
}
