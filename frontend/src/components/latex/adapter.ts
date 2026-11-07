import type { CompileResult, SourceInfo, SourceResult } from '@/lib/types'

/** Ce que l'éditeur de code LaTeX doit savoir d'un document : le CV ou sa lettre. */
export interface LatexAdapter {
  // Change quand le document change : le code est alors relu.
  key: string
  load: () => Promise<SourceInfo>
  save: (tex: string) => Promise<SourceResult>
  // Après un enregistrement : la compilation et le mode, pour l'aperçu et les bandeaux.
  onSaved: (result: SourceResult) => void
  recompile: () => void
  manual: boolean
  // Lecture seule, avec la raison affichée.
  locked: string | null
  compile: CompileResult | null
  texUrl: string
  fileName: string
  texts: {
    generated: string
    manual: string
    confirmTitle: string
    confirmText: string
  }
}
