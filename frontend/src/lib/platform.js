/**
 * Platform abstraction for TrainWithBrain.
 *
 * Website-first strategy: the app runs as a normal website, progressively
 * enhances into a Telegram Web App when opened inside Telegram, and can be
 * installed as a PWA. All platform-specific access goes through this module
 * so components stay clean and degrade gracefully everywhere.
 */

// The Telegram WebApp SDK is loaded with `async` (see public/index.html) so a
// slow/unreachable telegram.org never blocks first paint. So we must not capture
// window.Telegram at module load: read it lazily and, where needed, wait for it.
function getTg() {
  return (
    (typeof window !== "undefined" && window.Telegram && window.Telegram.WebApp) ||
    null
  );
}

/**
 * In a normal browser the Telegram SDK (if loaded) still creates
 * window.Telegram.WebApp, but `platform` is "unknown" and there is no init data.
 * A real Telegram client provides a real platform and/or user/init data.
 */
export function isTelegram() {
  const tg = getTg();
  if (!tg) return false;
  const hasUser = !!(tg.initDataUnsafe && tg.initDataUnsafe.user);
  const realPlatform = !!(tg.platform && tg.platform !== "unknown");
  const hasInit = !!(tg.initData && tg.initData.length > 0);
  return hasUser || realPlatform || hasInit;
}

export function isStandalonePWA() {
  if (typeof window === "undefined") return false;
  const mql = window.matchMedia ? window.matchMedia("(display-mode: standalone)") : null;
  return (mql && mql.matches === true) || window.navigator.standalone === true;
}

/** "telegram" | "pwa" | "web" */
export function getEnv() {
  if (isTelegram()) return "telegram";
  if (isStandalonePWA()) return "pwa";
  return "web";
}

/** Telegram platform string: ios | android | tdesktop | macos | web | weba | "web" (fallback). */
export function getPlatform() {
  const tg = getTg();
  return (tg && tg.platform) || "web";
}

export function getTelegram() {
  return getTg();
}

export function getTelegramUser() {
  const tg = getTg();
  return (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || null;
}

/** start_param from a deep link: https://t.me/<bot>?startapp=<param> */
export function getStartParam() {
  const tg = getTg();
  return (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || null;
}

// ---------------------------------------------------------------------------
// Web guest identity (so a website visitor keeps their data per-browser)
// ---------------------------------------------------------------------------
const WEB_UID_KEY = "twb_web_uid";
const WEB_NAME_KEY = "twb_web_name";

export function getOrCreateWebUser() {
  let uid = null;
  let name = "\u0413\u043e\u0441\u0442\u044c"; // "Гость"
  try {
    uid = window.localStorage.getItem(WEB_UID_KEY);
    if (!uid) {
      // Large positive int range, distinct from real Telegram ids in practice.
      uid = String(900000000000 + Math.floor(Math.random() * 100000000000));
      window.localStorage.setItem(WEB_UID_KEY, uid);
    }
    name = window.localStorage.getItem(WEB_NAME_KEY) || name;
  } catch (e) {
    uid = uid || "900000000001";
  }
  return {
    id: Number(uid),
    first_name: name,
    last_name: null,
    username: "web_guest",
    language_code: ((typeof navigator !== "undefined" && navigator.language) || "ru").slice(0, 2),
  };
}

export function setWebUserName(name) {
  try {
    window.localStorage.setItem(WEB_NAME_KEY, name || "");
  } catch (e) {
    /* no-op */
  }
}

// ---------------------------------------------------------------------------
// Haptics (safe no-op fallback off-Telegram)
// ---------------------------------------------------------------------------
export function haptic(style = "light") {
  const tg = getTg();
  try {
    tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred && tg.HapticFeedback.impactOccurred(style);
  } catch (e) {
    /* no-op */
  }
}

export function hapticNotify(type = "success") {
  const tg = getTg();
  try {
    tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred && tg.HapticFeedback.notificationOccurred(type);
  } catch (e) {
    /* no-op */
  }
}

export function hapticSelection() {
  const tg = getTg();
  try {
    tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged && tg.HapticFeedback.selectionChanged();
  } catch (e) {
    /* no-op */
  }
}

// ---------------------------------------------------------------------------
// Telegram theme (respect Telegram colors, keep brand dark header/background)
// ---------------------------------------------------------------------------
export function getThemeParams() {
  const tg = getTg();
  return (tg && tg.themeParams) || {};
}

export function getColorScheme() {
  const tg = getTg();
  return (tg && tg.colorScheme) || "dark";
}

export function applyTheme() {
  const tg = getTg();
  if (!tg) return;
  try {
    const tp = tg.themeParams || {};
    const root = document.documentElement;
    Object.keys(tp).forEach((k) => {
      root.style.setProperty(`--tg-${k.replace(/_/g, "-")}`, tp[k]);
    });
    root.setAttribute("data-color-scheme", tg.colorScheme || "dark");
    // Keep the brand dark chrome regardless of Telegram light/dark scheme
    tg.setHeaderColor && tg.setHeaderColor("#1C1C1C");
    tg.setBackgroundColor && tg.setBackgroundColor("#1C1C1C");
  } catch (e) {
    /* no-op */
  }
}

export function onThemeChange(cb) {
  const tg = getTg();
  if (!tg || !tg.onEvent) return () => {};
  tg.onEvent("themeChanged", cb);
  return () => {
    try {
      const t = getTg();
      t && t.offEvent && t.offEvent("themeChanged", cb);
    } catch (e) {
      /* no-op */
    }
  };
}

// ---------------------------------------------------------------------------
// PWA install prompt
// ---------------------------------------------------------------------------
let deferredPrompt = null;

export function initPlatform() {
  if (typeof window === "undefined") return;

  const exposeEnv = () => {
    try {
      const html = document.documentElement;
      html.setAttribute("data-env", getEnv());
      html.setAttribute("data-platform", getPlatform());
    } catch (e) {
      /* no-op */
    }
  };

  // Telegram enhancement: run when the SDK becomes available. Because the script
  // is loaded `async`, window.Telegram.WebApp might appear a moment after React
  // boots, so we retry for a short window and notify listeners when detected.
  const enhanceTelegram = () => {
    const tg = getTg();
    if (!tg) return;
    try {
      tg.ready();
      tg.expand();
      applyTheme();
      onThemeChange(applyTheme);
    } catch (e) {
      /* no-op */
    }
    exposeEnv();
    window.dispatchEvent(new CustomEvent("twb:telegram-ready"));
  };
  enhanceTelegram();
  if (!getTg()) {
    let tries = 0;
    const id = window.setInterval(() => {
      tries += 1;
      if (getTg()) {
        window.clearInterval(id);
        enhanceTelegram();
      } else if (tries >= 40) {
        // ~4s: no Telegram SDK — stay a plain website (graceful).
        window.clearInterval(id);
        exposeEnv();
      }
    }, 100);
  }

  // Expose environment on <html> for optional CSS hooks
  exposeEnv();

  // Capture the install prompt so we can offer a custom "Install" affordance
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    window.dispatchEvent(new CustomEvent("twb:installable", { detail: true }));
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    window.dispatchEvent(new CustomEvent("twb:installed"));
  });
}

export function canInstall() {
  return !!deferredPrompt;
}

export async function promptInstall() {
  if (!deferredPrompt) return false;
  try {
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    deferredPrompt = null;
    window.dispatchEvent(new CustomEvent("twb:installable", { detail: false }));
    return outcome === "accepted";
  } catch (e) {
    return false;
  }
}
