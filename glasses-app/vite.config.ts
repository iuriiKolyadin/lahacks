import { defineConfig } from 'vite'

// LAN_IP is set by `npm run qr` (scripts/qr.mjs). Pinning the HMR host to it
// stops the phone's WebView from trying to reach `localhost` for hot reload.
const lanIp = process.env.LAN_IP

export default defineConfig({
  // Relative asset paths, so the packaged .ehpk works wherever the host serves it from.
  base: './',
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    hmr: lanIp ? { host: lanIp } : undefined,
  },
  build: { target: 'esnext' },
})
