import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        // Дев-сервер проксирует API и WebSocket на бэкенд, чтобы работать
        // в браузере с того же origin без CORS.
        proxy: {
            '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
            '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
        },
    },
});
