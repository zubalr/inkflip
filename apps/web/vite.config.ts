import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define: {
    // Read-only inspection handle for gates/devtools — on in dev builds,
    // on in production only when INKFLIP_TEST_HOOKS=1 is set at build
    // time (the G1 gate build opts in; shipped builds do not).
    __INKFLIP_TEST_HOOKS__: JSON.stringify(
      mode === "development" || process.env.INKFLIP_TEST_HOOKS === "1",
    ),
  },
  server: {
    port: 5181,
    strictPort: true,
  },
  preview: {
    port: 5181,
    strictPort: true,
  },
}));
