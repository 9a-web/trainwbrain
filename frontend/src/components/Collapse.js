import { useEffect, useLayoutEffect, useRef } from "react";

const DURATION_OPEN = 320;
const DURATION_CLOSE = 240;
const EASING = "cubic-bezier(0.22, 1, 0.36, 1)";

/**
 * Плавное раскрытие/сворачивание блока по высоте.
 *
 * CSS не умеет анимировать `height: auto`, поэтому высоту меряем на месте
 * через Web Animations API: без сторонних библиотек и без нагрузки на бандл.
 * Контент остаётся в DOM (иначе нечего анимировать при закрытии) и помечен
 * `inert`, чтобы в свёрнутом виде поля не получали фокус.
 */
const Collapse = ({ open, children, className = "", innerClassName = "" }) => {
  const outerRef = useRef(null);
  const animationRef = useRef(null);
  const isFirstRender = useRef(true);

  // useLayoutEffect — чтобы свёрнутая карточка не мелькнула раскрытой
  // на первом кадре после монтирования.
  useLayoutEffect(() => {
    const el = outerRef.current;
    if (!el) return undefined;

    // Первый рендер — сразу в нужном состоянии, без «прыжка» анимации.
    if (isFirstRender.current) {
      isFirstRender.current = false;
      el.style.height = open ? "auto" : "0px";
      return undefined;
    }

    const startHeight = el.getBoundingClientRect().height;
    if (open) el.style.height = "auto"; // чтобы измерить итоговую высоту контента
    const endHeight = open ? el.getBoundingClientRect().height : 0;
    el.style.height = `${startHeight}px`;

    if (animationRef.current) animationRef.current.cancel();
    const animation = el.animate(
      [{ height: `${startHeight}px` }, { height: `${endHeight}px` }],
      { duration: open ? DURATION_OPEN : DURATION_CLOSE, easing: EASING },
    );
    animationRef.current = animation;
    animation.onfinish = () => {
      el.style.height = open ? "auto" : "0px";
    };
    return undefined;
  }, [open]);

  useEffect(
    () => () => {
      if (animationRef.current) animationRef.current.cancel();
    },
    [],
  );

  return (
    <div
      ref={outerRef}
      className={`ex-collapse ${className}`.trim()}
      data-open={open ? "true" : "false"}
      aria-hidden={open ? undefined : "true"}
    >
      <div className={`ex-collapse-inner ${innerClassName}`.trim()} inert={!open}>
        {children}
      </div>
    </div>
  );
};

export default Collapse;
