// ESLint flat config (v9+). React + TypeScript + Prettier-compatible.
// Linting rules only — formatting (line width, quotes, etc.) lives in .prettierrc.json.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { react, "react-hooks": reactHooks },
    languageOptions: {
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // Vite + React 18 → no need to import React for JSX
      "react/react-in-jsx-scope": "off",
      // We rely on TypeScript for prop validation
      "react/prop-types": "off",
    },
  },
  // ── HMVS gateway containment ───────────────────────────────────────────────
  // src/lib/hmvs.ts is the ONLY module allowed to reach the upstream HMVS
  // endpoints (/pharmapi/hmvs/*), and HMVS may be invoked exclusively from the
  // dispense flow (see docs/hmvs-scope.md). This rule fails the build if any
  // module imports the gateway; the override directly below re-permits the
  // dispense flow. To grow the dispense flow, add files to that override list.
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // External importers reach the gateway as `…/lib/hmvs`; siblings
              // inside src/lib reach it as `./hmvs` (or `../hmvs` from a subdir).
              // Cover all three so nothing outside the dispense flow can slip in.
              group: ["**/lib/hmvs", "**/lib/hmvs.*", "./hmvs", "./hmvs.*", "../hmvs", "../hmvs.*"],
              message:
                "HMVS is dispense-only: import src/lib/hmvs.ts only from the dispense flow (see docs/hmvs-scope.md).",
            },
          ],
        },
      ],
    },
  },
  // The dispense flow is the sole permitted importer of the HMVS gateway.
  {
    files: ["src/components/DispenseWizard.tsx"],
    rules: { "no-restricted-imports": "off" },
  },
  // Must be last: turns off ESLint rules that would conflict with Prettier output.
  prettier,
);
