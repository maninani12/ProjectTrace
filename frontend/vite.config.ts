import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5181,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8011",
      "/health": "http://127.0.0.1:8011",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.tsx"],
    pool: "threads",
    maxWorkers: 1,
  },
});
