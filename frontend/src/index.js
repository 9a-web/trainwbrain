import React from "react";
import ReactDOM from "react-dom/client";
// Шрифты — локальные @font-face (без внешнего @import, он блокировал рендер).
import "@/styles/fonts.css";
import "@/index.css";
import "@/styles/platform.css";
import App from "@/App";
import "@/styles/animations.css";
import "@/styles/toast-glass.css";
import { initPlatform } from "@/lib/platform";
import { lockZoom } from "@/lib/lockZoom";
import * as serviceWorkerRegistration from "@/serviceWorkerRegistration";

// Detect environment (Telegram / PWA / web), enhance Telegram, capture install prompt.
initPlatform();

// No pinch-to-zoom: the layout is a fixed-size mobile UI, zoom only breaks it.
lockZoom();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Register the PWA service worker (network-first; safe in dev).
serviceWorkerRegistration.register();
