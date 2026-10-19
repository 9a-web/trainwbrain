import React, { useEffect, useState } from "react";
import { canInstall, promptInstall } from "@/lib/platform";
import "@/components/InstallPrompt.css";

/**
 * Subtle, theme-consistent "Install app" affordance.
 * Renders only when the browser reports the app is installable (PWA).
 * On platforms without beforeinstallprompt (e.g. iOS Safari, Telegram) it
 * stays hidden and users rely on native "Add to Home Screen".
 */
export default function InstallPrompt() {
  const [show, setShow] = useState(canInstall());

  useEffect(() => {
    const onInstallable = (e) => {
      const detail = e && e.detail;
      setShow(detail === undefined ? canInstall() : !!detail);
    };
    const onInstalled = () => setShow(false);
    window.addEventListener("twb:installable", onInstallable);
    window.addEventListener("twb:installed", onInstalled);
    return () => {
      window.removeEventListener("twb:installable", onInstallable);
      window.removeEventListener("twb:installed", onInstalled);
    };
  }, []);

  if (!show) return null;

  return (
    <button
      type="button"
      className="twb-install-btn"
      data-testid="install-pwa-btn"
      onClick={() => {
        promptInstall();
      }}
    >
      <span className="twb-install-dot" aria-hidden="true" />
      Установить приложение
    </button>
  );
}
