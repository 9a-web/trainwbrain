/**
 * Отключает масштабирование приложения жестами (pinch-to-zoom).
 *
 * Основную работу делают meta viewport (user-scalable=no) и
 * `touch-action: pan-x pan-y` в index.css. Но iOS Safari и WKWebView
 * (в т.ч. Telegram на iPhone) исторически игнорируют user-scalable=no,
 * поэтому там дополнительно гасим gesture-события и мультитач-жесты.
 *
 * На остальных платформах ничего не навешиваем: лишний non-passive
 * touchmove-обработчик только замедлил бы скролл.
 */
const isIOS = () => {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  // iPadOS 13+ представляется как MacIntel, поэтому проверяем maxTouchPoints.
  return /iP(hone|ad|od)/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
};

export function lockZoom() {
  if (typeof document === "undefined") return;
  if (!isIOS()) return;

  const prevent = (event) => {
    if (event.cancelable) event.preventDefault();
  };

  // Safari-специфичные gesture-события (pinch) + страховка на мультитач.
  ["gesturestart", "gesturechange", "gestureend"].forEach((type) =>
    document.addEventListener(type, prevent, { passive: false }),
  );
  document.addEventListener(
    "touchmove",
    (event) => {
      if (event.touches.length > 1) prevent(event);
    },
    { passive: false },
  );
}
