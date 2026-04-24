import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  base: '/',
  server: {
    port: 5173,
    proxy: {
      '/command': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/reply': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/pair': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/pairing-code': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/jobs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },

      '/stream': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: '../ui',
    emptyOutDir: true,
  },
});
