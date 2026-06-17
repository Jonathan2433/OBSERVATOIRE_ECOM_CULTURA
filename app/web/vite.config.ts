import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En dev, on proxifie /api vers l'API locale ; en prod c'est nginx qui le fait.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
