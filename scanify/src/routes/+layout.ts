// Disable SSR and prerendering for the entire app.  The scanner is a
// client-only SPA — all data comes from the backend API / WebSocket at
// runtime, not at build time.  This keeps the build adapter-agnostic:
// adapter-auto just copies the SPA shell, and adapter-static (Tauri)
// emits the same index.html fallback.

export const ssr = false;
export const prerender = false;
