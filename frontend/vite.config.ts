import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  // Préparées dès le démarrage : sinon Vite les découvre à la première ouverture
  // de l'onglet LaTeX ou de la palette, et recharge la page.
  optimizeDeps: {
    include: [
      '@monaco-editor/react',
      'monaco-editor/esm/vs/editor/editor.api',
      'monaco-editor/esm/vs/editor/edcore.main',
      'cmdk',
    ],
  },
  server: {
    // Les essais de l'interface (make e2e) tournent sur d'autres ports.
    port: Number(process.env.CVB_PORT ?? 5173),
    strictPort: true,
    proxy: { '/api': process.env.CVB_API ?? 'http://127.0.0.1:8000' },
  },
})
