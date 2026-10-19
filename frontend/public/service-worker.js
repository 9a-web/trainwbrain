/* TrainWithBrain PWA service worker.
   Strategy: network-first (so online users always get fresh content and
   dev HMR keeps working), with an offline app-shell fallback from cache.
   Never intercepts API, cross-origin, or dev-socket requests. */

const CACHE = "twb-cache-v1";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/TWBlogo.png",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL).catch(() => {}))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  let url;
  try {
    url = new URL(req.url);
  } catch (e) {
    return;
  }

  // Only handle same-origin GET; never touch API, cross-origin, or dev sockets.
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api")) return;
  if (
    url.pathname.includes("hot-update") ||
    url.pathname.startsWith("/ws") ||
    url.pathname.startsWith("/sockjs-node")
  ) {
    return;
  }

  event.respondWith(
    (async () => {
      try {
        const fresh = await fetch(req);
        const cache = await caches.open(CACHE);
        cache.put(req, fresh.clone()).catch(() => {});
        return fresh;
      } catch (err) {
        const cached = await caches.match(req);
        if (cached) return cached;
        if (req.mode === "navigate") {
          const shell = await caches.match("/");
          if (shell) return shell;
        }
        throw err;
      }
    })()
  );
});
