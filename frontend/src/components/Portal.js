import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Portal — рендерит children в отдельный контейнер на <body>.
 *
 * Нужен для модальных окон: их оверлеи используют position: fixed, но если
 * любой предок имеет transform/filter/perspective (например, entrance-анимация
 * .date-selector с animation-fill-mode: both оставляет transform: translateY(0)),
 * то fixed привязывается к этому предку, а не к viewport — и модалка центрируется
 * не по экрану. Портал в body гарантирует центрирование по экрану пользователя.
 *
 * События React по-прежнему всплывают по дереву React (не DOM), поэтому
 * onClick на оверлее и stopPropagation на модалке продолжают работать.
 */
export default function Portal({ children }) {
  const [el] = useState(() => {
    const node = document.createElement("div");
    node.className = "twb-portal";
    return node;
  });

  useEffect(() => {
    document.body.appendChild(el);
    return () => {
      if (el.parentNode) el.parentNode.removeChild(el);
    };
  }, [el]);

  return createPortal(children, el);
}
