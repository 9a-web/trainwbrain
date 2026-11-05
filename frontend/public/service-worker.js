/* TrainWithBrain PWA service worker.
   Strategy: network-first (so online users always get fresh content and
   dev HMR keeps working), with an offline app-shell fallback from cache.
   Never intercepts API, cross-origin, or dev-socket requests. */

const CACHE = "twb-cache-v3";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/TWBlogo.png",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

/** Навигация и HTML — это «точка входа» в приложение: в index.html лежат
 *  имена хэшированных бандлов, и если отдать его из HTTP-кэша после деплоя,
 *  browser попросит уже удалённый main.<oldhash>.js и получит 404 — белый
 *  экран. Поэтому запрашиваем HTML мимо кэша (cache: "no-store"). */
const isDocument = (req, url) =>
  req.mode === "navigate" ||
  url.pathname === "/" ||
  url.pathname.endsWith(".html");

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

  const doc = isDocument(req, url);

  event.respondWith(
    (async () => {
      try {
        const fresh = await fetch(req, doc ? { cache: "no-store" } : undefined);
        // Хэшированные ассеты (/static/, /fonts/) неизменяемы — их кэшируем
        // на диск, а вот HTML каждый раз свежий, копию держим только для офлайна.
        const cache = await caches.open(CACHE);
        cache.put(req, fresh.clone()).catch(() => {});
        return fresh;
      } catch (err) {
        if (doc) {
          const shell = await caches.match("/index.html") || await caches.match("/");
          if (shell) return shell;
        }
        const cached = await caches.match(req);
        if (cached) return cached;
        throw err;
      }
    })()
  );
});
