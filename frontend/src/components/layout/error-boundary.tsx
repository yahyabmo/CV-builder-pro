import { CircleAlert, RotateCcw } from 'lucide-react'
import { Component, type ErrorInfo, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'

interface State {
  error: Error | null
}

/** Une erreur imprévue dans l'interface : un message et un bouton, jamais une page blanche. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Erreur de l’interface', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex h-dvh items-center justify-center bg-background p-8 text-center">
        <div className="flex max-w-md flex-col items-center gap-3">
          <CircleAlert className="size-7 text-destructive" />
          <p className="text-[15px] font-semibold">L'interface a rencontré une erreur</p>
          <p className="text-[12.5px] text-muted-foreground">
            Tes CV sont enregistrés sur le disque à chaque modification : recharger la page ne fait rien perdre.
          </p>
          <code className="max-w-full truncate rounded bg-muted px-2 py-1 font-mono text-[11px] text-muted-foreground">
            {this.state.error.message}
          </code>
          <Button size="sm" className="gap-1.5" onClick={() => window.location.reload()}>
            <RotateCcw className="size-3.5" /> Recharger
          </Button>
        </div>
      </div>
    )
  }
}
