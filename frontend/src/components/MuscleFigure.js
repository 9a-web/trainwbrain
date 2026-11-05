import React, { Suspense, lazy, useEffect, useRef, useState } from "react";
import { MuscleSilhouette } from "@/components/MuscleMap";

/**
 * Фигура для карты мышц: 3D-анатомическая модель (как в «Статистике») с
 * подсветкой групп. Если WebGL недоступен, чанк three.js не загрузился или
 * сцена упала — молча откатываемся на 2D-силуэт, чтобы карта всегда была.
 *
 * 3D монтируется только когда фигура подъехала к экрану: three.js — тяжёлый
 * чанк, и держать его на каждом экране незачем.
 */

const MuscleBody3D = lazy(() => import("@/components/MuscleBody3D"));

export function supportsWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch (e) {
    return false;
  }
}

/** Монтирует 3D только когда блок подъехал близко к экрану. */
export function useNearViewport(ref, margin = "260px") {
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (typeof IntersectionObserver === "undefined") {
      setNear(true);
      return undefined;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true);
          io.disconnect();
        }
      },
      { rootMargin: margin }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref, margin]);
  return near;
}

/** Если WebGL-сцена упала — молча откатываемся на 2D-силуэт. */
export class ThreeBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onFail?.();
  }

  render() {
    if (this.state.failed) return null;
    return this.props.children;
  }
}

export default function MuscleFigure({
  regions = {},
  selected = null,
  onSelect,
  view = "front",
  testPrefix = "mm",
}) {
  const [webgl] = useState(supportsWebGL);
  const [force2d, setForce2d] = useState(false);
  const wrapRef = useRef(null);
  const near = useNearViewport(wrapRef);
  const use3d = webgl && !force2d;

  return (
    <div className={`mf-figure ${use3d ? "mf-figure-3d" : ""}`} ref={wrapRef}>
      {use3d ? (
        near ? (
          <Suspense fallback={<div className="mb3d-loading" data-testid={`${testPrefix}-3d-loading`} />}>
            <ThreeBoundary onFail={() => setForce2d(true)}>
              <MuscleBody3D
                regions={regions}
                selected={selected}
                onSelect={onSelect}
                onFail={() => setForce2d(true)}
                view={view}
                testPrefix={`${testPrefix}-3d`}
              />
            </ThreeBoundary>
          </Suspense>
        ) : (
          <div className="mb3d-loading" data-testid={`${testPrefix}-3d-idle`} />
        )
      ) : (
        <MuscleSilhouette
          view={view}
          regions={regions}
          selected={selected}
          onSelect={onSelect}
          testPrefix={`${testPrefix}-silhouette`}
        />
      )}
    </div>
  );
}

export { MuscleBody3D };
