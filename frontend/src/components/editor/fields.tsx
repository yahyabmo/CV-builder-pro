import { useLayoutEffect, useRef, type ComponentProps } from 'react'

import { cn } from '@/lib/utils'

interface FieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  multiline?: boolean
  mono?: boolean
}

/** Un champ libellé, à hauteur automatique ; `multiline` autorise les retours à la ligne. */
export function Field({ label, value, onChange, placeholder, className, multiline, mono }: FieldProps) {
  return (
    <label className={cn('flex min-w-0 flex-col gap-1.5', className)}>
      <span className="text-[12px] font-medium text-foreground/75">{label}</span>
      <AutoTextarea
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        // Un champ d'une ligne passe à la ligne à l'affichage (rien n'est
        // coupé), mais la touche Entrée n'y ajoute pas de retour.
        onKeyDown={multiline ? undefined : (event) => event.key === 'Enter' && event.preventDefault()}
        className={cn(mono && 'font-mono text-[12px]')}
      />
    </label>
  )
}

/** Une zone de texte qui grandit avec son contenu, sans barre de défilement. */
export function AutoTextarea({ className, value, ...props }: ComponentProps<'textarea'>) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${element.scrollHeight + 2}px`
  }, [value])
  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      className={cn(
        'w-full min-w-0 resize-none overflow-hidden rounded-md border border-input bg-transparent px-2.5 py-1.5 text-[13px] leading-relaxed shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30',
        className,
      )}
      {...props}
    />
  )
}
