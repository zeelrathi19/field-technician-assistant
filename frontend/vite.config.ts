import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev only: the API is proxied so the browser sees one origin, like production.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", sourcemap: false },
});
