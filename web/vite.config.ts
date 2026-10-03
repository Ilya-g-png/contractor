import react from "@vitejs/plugin-react";
import browserslistToEsbuild from "browserslist-to-esbuild";
import { defineConfig } from "vitest/config";

const browserTargets = browserslistToEsbuild();

const apiProxy = { "/api": "http://127.0.0.1:8000" };

export default defineConfig({
  appType: "spa",
  plugins: [react()],
  build: {
    target: browserTargets,
    cssTarget: browserTargets,
    manifest: true,
    modulePreload: { polyfill: false },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: apiProxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: apiProxy,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.{ts,mjs}"],
    unstubGlobals: true,
    restoreMocks: true,
  },
});
