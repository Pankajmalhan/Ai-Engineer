import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The page calls /api/* on its own origin; in dev, Vite forwards that to the TypeScript agent layer.
// (A proxy also means no CORS setup, and the API key never reaches the browser -- it lives in ts-agent.)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': process.env.AGENT_URL ?? 'http://localhost:3000' },
  },
});
