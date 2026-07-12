import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        // Punto de entrada del Popup
        main: resolve(__dirname, 'index.html'),
        // Punto de entrada del Motor de Fondo
        background: resolve(__dirname, 'src/background.ts'),
      },
      output: {
        // Forzamos que el nombre sea fijo para que el manifest lo encuentre
        entryFileNames: (chunkInfo) => {
          return chunkInfo.name === 'background' ? '[name].js' : 'assets/[name]-[hash].js';
        },
      },
    },
  },
})
