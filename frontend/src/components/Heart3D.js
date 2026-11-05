import React, { useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

/**
 * 3D-сердце, бьющееся в ритме пульса пользователя.
 *
 * Рендерит процедурное сердце через THREE.ExtrudeGeometry + bevel
 * (замкнутая гладкая форма без отверстий).
 *
 * Для загрузки реальной модели сердца (GLB со Sketchfab):
 * 1. Скачайте файл со страницы https://sketchfab.com/3d-models/realistic-human-heart-3f8072336ce94d18b3d0d055a1ece089
 * 2. Переименуйте в realistic-heart.glb
 * 3. Поместите в public/models/hearts/realistic-heart.glb
 * 4. Heart3D загрузит его через GLTFLoader (см README.md в директории)
 *
 * Камера жёстко зафиксирована — вращение/зум невозможны.
 * Пульс синхронизирован с heartRate (BPM).
 * Если WebGL недоступен — анимированный SVG.
 */

const HEART_BPM_DEFAULT = 72;

/* ──── Строим процедурное сердце (ExtrudeGeometry + Bevel) ──── */
function buildFallbackHeart() {
  const shape = new THREE.Shape();
  /* Классический контур сердца через кубические кривые Безье */
  shape.moveTo(0.5, 0.5);
  shape.bezierCurveTo(0.5, 0.5, 0.4, 0, 0, 0);
  shape.bezierCurveTo(-0.6, 0, -0.6, 0.7, -0.6, 0.7);
  shape.bezierCurveTo(-0.6, 1.1, -0.3, 1.54, 0.5, 1.9);
  shape.bezierCurveTo(1.3, 1.54, 1.6, 1.1, 1.6, 0.7);
  shape.bezierCurveTo(1.6, 0.7, 1.6, 0, 1.0, 0);
  shape.bezierCurveTo(0.7, 0, 0.5, 0.5, 0.5, 0.5);

  const depth = 0.34;
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: true,
    bevelThickness: 0.14,
    bevelSize: 0.09,
    bevelSegments: 10,
    curveSegments: 28,
  });
  geo.translate(-0.5, -0.9, -depth / 2);
  geo.computeVertexNormals();
  return geo;
}

/* ──── BeatingHeart: анимирует mesh в ритме BPM ──── */
function BeatingHeart({ heartRate, geometry }) {
  const meshRef = useRef();
  const bpm = heartRate && heartRate > 0 ? heartRate : HEART_BPM_DEFAULT;

  useFrame((state) => {
    if (!meshRef.current) return;
    const period = 60 / bpm;
    const t = (state.clock.elapsedTime % period) / period;
    const curve =
      t < 0.2
        ? 1 + 0.085 * Math.sin((t / 0.2) * (Math.PI * 0.5))
        : 1 + 0.085 * Math.cos(((t - 0.2) / 0.8) * (Math.PI * 0.5));
    const s = Math.max(0.93, curve);
    meshRef.current.scale.set(s, s, s);
  });

  return (
    <mesh ref={meshRef} geometry={geometry} castShadow>
      <meshPhysicalMaterial
        color="#b42334"
        roughness={0.44}
        metalness={0.1}
        clearcoat={0.05}
        sheen={0.35}
        sheenColor="#ff6a5a"
        emissive="#6e1420"
        emissiveIntensity={0.22}
      />
    </mesh>
  );
}

/* ──── SVG fallback (WebGL недоступен) ──── */
function HeartFallback({ heartRate }) {
  const bpm = heartRate && heartRate > 0 ? heartRate : HEART_BPM_DEFAULT;
  return (
    <svg
      viewBox="0 0 100 100"
      style={{ width: "100%", height: "100%", display: "block" }}
      role="img"
      aria-label="Сердце"
    >
      <defs>
        <radialGradient id="hfbg" cx="35%" cy="30%" r="80%">
          <stop offset="0%" stopColor="#e2625a" />
          <stop offset="60%" stopColor="#a51f2f" />
          <stop offset="100%" stopColor="#7a1420" />
        </radialGradient>
      </defs>
      <path
        d="M50 84 C 18 62, 8 40, 22 26 C 30 18, 42 20, 50 30 C 58 20, 70 18, 78 26 C 92 40, 82 62, 50 84 Z"
        fill="url(#hfbg)"
        stroke="#ff9d86"
        strokeWidth="1.4"
        style={{ animation: `cd-heart-fallback-beat ${(60 / bpm).toFixed(2)}s ease-in-out infinite` }}
      />
    </svg>
  );
}

/* ──── Export ──── */
export default function Heart3D({ heartRate }) {
  const [glFailed, setGlFailed] = useState(false);
  const fallbackGeo = useMemo(() => buildFallbackHeart(), []);

  return (
    <div className="cd-heart-model">
      {glFailed ? (
        <HeartFallback heartRate={heartRate} />
      ) : (
        <Canvas
          dpr={[1, 1.5]}
          gl={{ antialias: true, alpha: true, failIfMajorPerformanceCaveat: false }}
          camera={{ position: [0, 0.25, 3.4], fov: 32, near: 0.08, far: 8 }}
          style={{ width: "100%", height: "100%" }}
          fallback={<HeartFallback heartRate={heartRate} />}
          onCreated={({ gl }) => { gl.setClearColor(0x000000, 0); }}
          onContextLost={() => setGlFailed(true)}
        >
          <ambientLight intensity={0.55} />
          <directionalLight position={[1.4, 2.2, 3.6]} intensity={0.9} />
          <directionalLight position={[-0.8, 0.3, 2.4]} intensity={0.3} />
          <directionalLight position={[0, -1.5, 1.2]} intensity={0.15} />
          <BeatingHeart heartRate={heartRate} geometry={fallbackGeo} />
        </Canvas>
      )}
    </div>
  );
}