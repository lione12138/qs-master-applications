import js from "@eslint/js";
import globals from "globals";
import prettier from "eslint-config-prettier";

export default [
  {
    ignores: [
      "node_modules/**",
      "site/**",
      "data/**",
      "scripts/**",
      "**/*.min.js",
    ],
  },
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        GRADWINDOW_CONFIG: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    },
  },
  {
    // Cloudflare Worker: runs in a Workers runtime with Node-like globals.
    // Its input sanitizers intentionally match ASCII control characters.
    files: ["subscriptions/**/*.js"],
    languageOptions: {
      globals: { ...globals.node, ...globals.browser },
    },
    rules: {
      "no-control-regex": "off",
    },
  },
  prettier,
];
