import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";

// Two apps from one codebase: the candidate app (index.html → /) and the staff app (staff/index.html → /staff,
// /admin, /review). The backend serves the right one per path; this plugin does the same in `npm run dev`.
const STAFF = /^\/(staff|admin|review)(\/|$|\?)/;
const staffPages = (): Plugin => ({
  name: "fairproctor-staff-pages",
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      const url = req.url || "";
      if (STAFF.test(url) && !url.startsWith("/staff/index.html") && (req.headers.accept || "").includes("text/html")) {
        req.url = "/staff/index.html";
      }
      next();
    });
  },
});

// Dev: the FastAPI backend runs on :8000 (change the port if 8000 is busy).
export default defineConfig({
  plugins: [react(), tailwindcss(), staffPages()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { proxy: { "/api": process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000" } },
  build: {
    rollupOptions: {
      input: { main: path.resolve(__dirname, "index.html"), staff: path.resolve(__dirname, "staff/index.html") },
    },
  },
});
