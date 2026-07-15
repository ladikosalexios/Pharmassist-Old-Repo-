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
  // Must be last: turns off ESLint rules that would conflict with Prettier output.
  prettier,
);
