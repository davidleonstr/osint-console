import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// In development the React dev server runs on 5173 and proxies /api to Flask
// on 8420, so both hot reload and the live stream work from one origin.
// `vite build` emits into web/dist, which Flask serves directly in production.
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, process.cwd());

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API ?? 'http://127.0.0.1:8420',
          changeOrigin: true,
          // Server-Sent Events must not be buffered by the proxy.
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
                proxyRes.headers['cache-control'] = 'no-cache, no-transform';
              }
            });
          },
        },
      },
    },
    build: { outDir: 'dist', emptyOutDir: true },
  }
});
