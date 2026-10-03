import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

const storageMessage = "No client-side storage or cookies (FR-081, INV-W7).";
const serviceWorkerMessage = "No service worker (FR-076, INV-W7).";

export default defineConfig([
  globalIgnores(["dist", "coverage"]),
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [reactHooks.configs.flat["recommended-latest"], jsxA11y.flatConfigs.recommended],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "localStorage", message: storageMessage },
        { name: "sessionStorage", message: storageMessage },
        { name: "indexedDB", message: storageMessage },
      ],
      "no-restricted-properties": [
        "error",
        { object: "document", property: "cookie", message: storageMessage },
        { property: "localStorage", message: storageMessage },
        { property: "sessionStorage", message: storageMessage },
        { property: "indexedDB", message: storageMessage },
        { object: "navigator", property: "sendBeacon", message: storageMessage },
        { property: "serviceWorker", message: serviceWorkerMessage },
      ],
    },
  },
  {
    files: ["*.{js,ts}", "scripts/**/*.{js,mjs,ts}"],
    languageOptions: {
      globals: globals.node,
    },
  },
]);
