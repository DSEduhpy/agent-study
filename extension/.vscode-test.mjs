import { defineConfig } from "@vscode/test-cli";
import { fileURLToPath } from "node:url";

export default defineConfig({
  files: "test/**/*.test.js",
  extensionDevelopmentPath: fileURLToPath(new URL(".", import.meta.url)),
  workspaceFolder: fileURLToPath(new URL("..", import.meta.url))
});