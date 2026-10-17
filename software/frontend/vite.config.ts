import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8000', '/ws': { target: 'ws://127.0.0.1:8000', ws: true } } },
  preview: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8000', '/ws': { target: 'ws://127.0.0.1:8000', ws: true } } },
  build: { rollupOptions: { output: { manualChunks(id) {
    const path = id.replaceAll('\\', '/');
    if (path.includes('/node_modules/recharts/') || /\/node_modules\/d3-[^/]+\//.test(path)) return 'charts';
  } } } },
  test: { include: ['src/**/*.test.{ts,tsx}'], environment: 'jsdom', setupFiles: ['./src/test-setup.ts'], css: true },
});
