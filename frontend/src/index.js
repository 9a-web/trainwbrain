import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import "@/styles/platform.css";
import App from "@/App";
import "@/styles/animations.css";
import { initPlatform } from "@/lib/platform";
import * as serviceWorkerRegistration from "@/serviceWorkerRegistration";

// Detect environment (Telegram / PWA / web), enhance Telegram, capture install prompt.
initPlatform();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Register the PWA service worker (network-first; safe in dev).
serviceWorkerRegistration.register();
