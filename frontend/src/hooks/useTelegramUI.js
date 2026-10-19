import { useEffect, useRef } from "react";
import { getTelegram } from "@/lib/platform";

/**
 * Show Telegram's native BackButton while the component is mounted.
 * No-op outside Telegram (web/PWA use the in-app back control instead).
 */
export function useBackButton(enabled, handler) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const tg = getTelegram();
    if (!tg || !tg.BackButton || !enabled) return undefined;
    const cb = () => ref.current && ref.current();
    try {
      tg.BackButton.onClick(cb);
      tg.BackButton.show();
    } catch (e) {
      /* no-op */
    }
    return () => {
      try {
        tg.BackButton.offClick(cb);
        tg.BackButton.hide();
      } catch (e) {
        /* no-op */
      }
    };
  }, [enabled]);
}

/**
 * Drive Telegram's native MainButton. No-op outside Telegram.
 * opts: { enabled, text, visible, disabled, progress, onClick }
 */
export function useMainButton(opts) {
  const { enabled = true, text = "", visible = true, disabled = false, progress = false, onClick } = opts || {};
  const ref = useRef(onClick);
  ref.current = onClick;
  useEffect(() => {
    const tg = getTelegram();
    if (!tg || !tg.MainButton || !enabled) return undefined;
    const cb = () => ref.current && ref.current();
    try {
      tg.MainButton.setText(text || "");
      if (disabled) tg.MainButton.disable();
      else tg.MainButton.enable();
      if (progress && tg.MainButton.showProgress) tg.MainButton.showProgress();
      else if (tg.MainButton.hideProgress) tg.MainButton.hideProgress();
      tg.MainButton.onClick(cb);
      if (visible) tg.MainButton.show();
      else tg.MainButton.hide();
    } catch (e) {
      /* no-op */
    }
    return () => {
      try {
        tg.MainButton.offClick(cb);
        tg.MainButton.hide();
      } catch (e) {
        /* no-op */
      }
    };
  }, [enabled, text, visible, disabled, progress]);
}
