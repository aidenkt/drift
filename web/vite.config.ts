import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: { fs: { allow: [".."] } }, // read ../schema/fixtures
});
