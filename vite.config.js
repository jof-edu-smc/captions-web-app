import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendPort = env.PORT || '5001';

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': `http://localhost:${backendPort}`,
        '/audio': `http://localhost:${backendPort}`,
        '/files': `http://localhost:${backendPort}`,
      },
    },
  };
});