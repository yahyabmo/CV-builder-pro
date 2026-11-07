// Monaco servi en local (pas de CDN) : le cœur de l'éditeur, ses outils
// (recherche, repli, accolades) et une coloration LaTeX. Aucun autre langage.
import { loader } from '@monaco-editor/react'
import 'monaco-editor/esm/vs/editor/edcore.main'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'

self.MonacoEnvironment = { getWorker: () => new EditorWorker() }

monaco.languages.register({ id: 'latex', extensions: ['.tex'] })
monaco.languages.setLanguageConfiguration('latex', {
  comments: { lineComment: '%' },
  brackets: [
    ['{', '}'],
    ['[', ']'],
  ],
  autoClosingPairs: [
    { open: '{', close: '}' },
    { open: '[', close: ']' },
    { open: '$', close: '$' },
  ],
  surroundingPairs: [
    { open: '{', close: '}' },
    { open: '[', close: ']' },
  ],
})
monaco.languages.setMonarchTokensProvider('latex', {
  tokenizer: {
    root: [
      [/%.*$/, 'comment'],
      [/(\\(?:begin|end))(\{)([^}]*)(\})/, ['keyword', 'delimiter.curly', 'type', 'delimiter.curly']],
      [/\\[a-zA-Z@]+\*?/, 'keyword'],
      [/\\[^a-zA-Z@\s]/, 'keyword'],
      [/\$\$/, 'string', '@display'],
      [/\$/, 'string', '@math'],
      [/[{}]/, 'delimiter.curly'],
      [/[[\]]/, 'delimiter.square'],
      [/&/, 'operator'],
      [/-?\d*\.?\d+(?:pt|cm|mm|em|ex|in|bp|sp)\b/, 'number'],
    ],
    math: [
      [/[^$\\]+/, 'string'],
      [/\\./, 'string'],
      [/\$/, 'string', '@pop'],
    ],
    display: [
      [/[^$\\]+/, 'string'],
      [/\\./, 'string'],
      [/\$\$/, 'string', '@pop'],
    ],
  },
})

// Fonds accordés à l'interface (carte claire, carte sombre).
monaco.editor.defineTheme('cvb-light', {
  base: 'vs',
  inherit: true,
  rules: [{ token: 'type', foreground: '0f7b6c' }],
  colors: { 'editor.background': '#ffffff', 'editorLineNumber.foreground': '#a3a8b8' },
})
monaco.editor.defineTheme('cvb-dark', {
  base: 'vs-dark',
  inherit: true,
  rules: [{ token: 'type', foreground: '4ec9b0' }],
  colors: { 'editor.background': '#1b1d24', 'editorLineNumber.foreground': '#5f6577' },
})

loader.config({ monaco })

export { monaco }
