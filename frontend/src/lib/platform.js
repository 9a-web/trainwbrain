/**
 * Platform abstraction for TrainWithBrain.
 *
 * Website-first strategy: the app runs as a normal website, progressively
 * enhances into a Telegram Web App when opened inside Telegram, and can be
 * installed as a PWA. All platform-specific access goes through this module
 * so components stay clean and degrade gracefully everywhere.
 */

const tg =
  (typeof window !== "undefined" && window.Telegram && window.Telegram.WebApp) ||
  null;

/**
 * In a normal browser the Telegram SDK (if loaded) still creates
 * window.Telegram.WebApp, but `platform` is "unknown" and there is no init data.
 * A real Telegram client provides a real platform and/or user/init data.
 */
export function isTelegram() {
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
  return (tg && tg.platform) || "web";
}

export function getTelegram() {
  return tg;
}

export function getTelegramUser() {
  return (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || null;
}

/** start_param from a deep link: https://t.me/<bot>?startapp=<param> */
export function getStartParam() {
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
  try {
    tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred && tg.HapticFeedback.impactOccurred(style);
  } catch (e) {
    /* no-op */
  }
}

export function hapticNotify(type = "success") {
  try {
    tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred && tg.HapticFeedback.notificationOccurred(type);
  } catch (e) {
    /* no-op */
  }
}

export function hapticSelection() {
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
  return (tg && tg.themeParams) || {};
}

export function getColorScheme() {
  return (tg && tg.colorScheme) || "dark";
}

export function applyTheme() {
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
  if (!tg || !tg.onEvent) return () => {};
  tg.onEvent("themeChanged", cb);
  return () => {
    try {
      tg.offEvent("themeChanged", cb);
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

  // Telegram enhancement
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      applyTheme();
      onThemeChange(applyTheme);
    } catch (e) {
      /* no-op */
    }
  }

  // Expose environment on <html> for optional CSS hooks
  try {
    const html = document.documentElement;
    html.setAttribute("data-env", getEnv());
    html.setAttribute("data-platform", getPlatform());
  } catch (e) {
    /* no-op */
  }

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
