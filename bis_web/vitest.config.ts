import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  // The app relies on the automatic JSX runtime (no `import React` in every
  // file). esbuild defaults to the classic runtime, which would demand a React
  // import that the components deliberately do not have.
  esbuild: { jsx: "automatic" },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
