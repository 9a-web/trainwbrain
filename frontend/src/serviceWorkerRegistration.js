/* Minimal service worker registration for PWA installability + offline shell.
   Registers over HTTPS (or localhost). The SW itself is network-first, so this
   is safe to run in development without breaking hot reload. */

export function register() {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) return;

  const host = window.location.hostname;
  const isLocalhost = host === "localhost" || host === "127.0.0.1" || host === "[::1]";
  const isSecure = window.location.protocol === "https:" || isLocalhost;
  if (!isSecure) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/service-worker.js")
      .catch(() => {});
  });
}

export function unregister() {
  if ("serviceWorker" in navigator && navigator.serviceWorker.getRegistrations) {
    navigator.serviceWorker
      .getRegistrations()
      .then((regs) => regs.forEach((r) => r.unregister()))
      .catch(() => {});
  }
}
