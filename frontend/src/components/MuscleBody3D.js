import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { muscleLabel } from "@/lib/muscles";
import ANATOMY_MAP from "@/lib/anatomyMap.json";
import "./MuscleBody3D.css";

/**
 * 3D-карта мышц на реальной анатомической модели (écorché).
 *
 * Модель: 634 отдельные структуры — скелет и каждая скелетная мышца своим
 * мешем (BodyParts3D + Z-Anatomy, CC BY-SA 4.0, см. public/models/ATTRIBUTION.md).
 * Каждый меш сопоставлен одной из 20 тренировочных групп (lib/anatomyMap.json),
 * поэтому подсветка честная: объём «груди» красит именно грудные, а не силуэт.
 *
 * Запечённое затенение из вершинных цветов пересчитывается в нейтральную
 * яркость на лету, чтобы цвет группы ложился чисто, но сохранял объём.
 */

const MODEL_URL = `${process.env.PUBLIC_URL || ""}/models/ecorche.meshopt.glb`;

const GROUPS = [
  "chest", "abs", "obliques", "front_delts", "side_delts", "rear_delts",
  "biceps", "triceps", "forearms", "traps", "neck", "upper_back", "lats",
  "lower_back", "glutes", "quads", "hamstrings", "adductors", "abductors", "calves",
];

// Мышечная ткань (покой) → бренд-оранжевый → жёлтый (максимум периода)
const C_IDLE = new THREE.Color("#6d2a26");
const C_MID = new THREE.Color("#ff7a18");
const C_MAX = new THREE.Color("#ffd60a");
const BONE = new THREE.Color("#cfc9bb");

const BODY_HEIGHT = 1.9; // к чему нормируем рост модели
const FOV = 30;

const isDebug = () => typeof window !== "undefined" && /[?&]mmdebug=1/.test(window.location.search);

function muscleColor(intensity) {
  const k = Math.min(1, Math.max(0, Number(intensity) || 0));
  if (k <= 0.002) return C_IDLE.clone();
  if (k < 0.34) return C_IDLE.clone().lerp(C_MID, k / 0.34);
  return C_MID.clone().lerp(C_MAX, (k - 0.34) / 0.66);
}

/**
 * Вершинные цвета модели — «оттенок ткани × запечённое затенение».
 * Оставляем только яркость (затенение), нормируя по 98-му перцентилю меша,
 * иначе цвет группы умножится на красноватый оттенок ткани и станет грязным.
 */
function normalizeAOVertexColors(geom) {
  const attr = geom.getAttribute("color");
  if (!attr || !attr.array) return;
  const a = attr.array;
  const n = attr.count;
  if (!n) return;
  const lum = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    const j = i * 4;
    lum[i] = 0.2126 * a[j] + 0.7152 * a[j + 1] + 0.0722 * a[j + 2];
  }
  const sorted = Array.from(lum).sort((x, y) => x - y);
  const p98 = sorted[Math.min(n - 1, Math.floor(n * 0.98))] || 1;
  const scale = 255 / Math.max(1, p98);
  for (let i = 0; i < n; i += 1) {
    const j = i * 4;
    const v = Math.min(255, Math.round(lum[i] * scale * 1.06));
    a[j] = v;
    a[j + 1] = v;
    a[j + 2] = v;
  }
  attr.needsUpdate = true;
}

/** Имя структуры из glTF (с учётом дедупликации имён в GLTFLoader). */
function resolveGroup(o) {
  const raw = o.userData?.name || o.name || "";
  return (
    ANATOMY_MAP[raw] ||
    ANATOMY_MAP[String(raw).replace(/_\d+$/, "")] ||
    ANATOMY_MAP[String(o.name || "").replace(/_\d+$/, "")] ||
    null
  );
}

function makeMuscleMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.52,
    metalness: 0.14,
    vertexColors: true,
    emissive: new THREE.Color(0x000000),
    emissiveIntensity: 1,
  });
}

/* ------------------------------------------------------------------ */
/* загрузка и подготовка модели                                       */
/* ------------------------------------------------------------------ */

function useEcorche() {
  const [status, setStatus] = useState("loading");
  const [progress, setProgress] = useState(0);
  const [assets, setAssets] = useState(null);

  useEffect(() => {
    let alive = true;
    const manager = new THREE.LoadingManager();
    manager.onProgress = (_u, loaded, total) => {
      if (alive && total) setProgress(Math.min(1, loaded / total));
    };
    const loader = new GLTFLoader(manager);
    loader.setMeshoptDecoder(MeshoptDecoder);

    loader
      .loadAsync(MODEL_URL)
      .then((gltf) => {
        if (!alive) return;
        const groupMats = {};
        GROUPS.forEach((k) => { groupMats[k] = makeMuscleMaterial(); });
        const boneMat = new THREE.MeshStandardMaterial({
          color: BONE.clone(),
          roughness: 0.62,
          metalness: 0.06,
          vertexColors: true,
        });

        const hitMeshes = [];
        const allMeshes = [];
        const geoms = new Set();
        let muscleMeshes = 0;

        gltf.scene.traverse((o) => {
          if (!o.isMesh) return;
          allMeshes.push(o);
          const key = resolveGroup(o);
          if (key && groupMats[key]) {
            o.material = groupMats[key];
            o.userData.group = key;
            hitMeshes.push(o);
            muscleMeshes += 1;
          } else {
            o.material = boneMat;
            o.userData.group = null;
          }
          o.castShadow = true;
          o.receiveShadow = true;
          o.frustumCulled = true;
          if (!geoms.has(o.geometry)) {
            geoms.add(o.geometry);
            normalizeAOVertexColors(o.geometry);
          }
        });

        const box = new THREE.Box3().setFromObject(gltf.scene);
        const size = box.getSize(new THREE.Vector3());
        const scale = BODY_HEIGHT / (size.y || 1);

        if (alive) {
          setAssets({
            scene: gltf.scene,
            groupMats,
            boneMat,
            hitMeshes,
            pickMeshes: allMeshes,
            muscleMeshes,
            box,
            size,
            scale,
            footOffset: box.min.y * scale,
            centerY: box.getCenter(new THREE.Vector3()).y * scale,
          });
          setStatus("ready");
        }
      })
      .catch(() => {
        if (alive) setStatus("error");
      });

    return () => {
      alive = false;
    };
  }, []);

  return { status, progress, assets };
}

/* ------------------------------------------------------------------ */
/* сцена                                                              */
/* ------------------------------------------------------------------ */

function Environment() {
  const { scene, gl } = useThree();
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const room = new RoomEnvironment();
    const tex = pmrem.fromScene(room, 0.04).texture;
    scene.environment = tex;
    scene.environmentIntensity = 0.42;
    pmrem.dispose();
    return () => {
      scene.environment = null;
      tex.dispose();
    };
  }, [scene, gl]);
  return null;
}

function Model({ assets, regions, selected, onSelect, onHover }) {
  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const { camera, gl } = useThree();

  // цвета групп: жара по объёму + затемнение невыбранных
  useEffect(() => {
    const dim = !!selected;
    GROUPS.forEach((k) => {
      const region = regions?.[k];
      const i = region ? Math.min(1, Math.max(0, Number(region.intensity_0_1) || 0)) : 0;
      const isSel = selected === k;
      const c = muscleColor(i);
      const mat = assets.groupMats[k];
      if (!mat) return;
      mat.color.copy(c).multiplyScalar(dim && !isSel ? 0.4 : 1);
      mat.emissive.copy(c).multiplyScalar((0.03 + 0.5 * i) * (dim && !isSel ? 0.18 : 1) * (isSel ? 1.8 : 1));
      mat.needsUpdate = true;
    });
    assets.boneMat.color.copy(BONE).multiplyScalar(dim ? 0.62 : 1);
    assets.boneMat.needsUpdate = true;
  }, [assets, regions, selected]);

  // диагностика кадрирования: проецируем bbox модели в экранные координаты
  useEffect(() => {
    if (!isDebug()) return undefined;
    const metrics = () => {
      camera.updateMatrixWorld();
      const box = new THREE.Box3().setFromObject(assets.scene);
      const min = box.min;
      const max = box.max;
      let xmin = 1, xmax = -1, ymin = 1, ymax = -1;
      for (let i = 0; i < 8; i += 1) {
        const v = new THREE.Vector3(
          i & 1 ? max.x : min.x,
          i & 2 ? max.y : min.y,
          i & 4 ? max.z : min.z
        ).project(camera);
        xmin = Math.min(xmin, v.x); xmax = Math.max(xmax, v.x);
        ymin = Math.min(ymin, v.y); ymax = Math.max(ymax, v.y);
      }
      const rect = gl.domElement.getBoundingClientRect();
      return {
        world: { min: min.toArray().map((n) => +n.toFixed(3)), max: max.toArray().map((n) => +n.toFixed(3)) },
        ndc: { xmin: +xmin.toFixed(3), xmax: +xmax.toFixed(3), ymin: +ymin.toFixed(3), ymax: +ymax.toFixed(3) },
        px: {
          left: +((xmin + 1) / 2 * rect.width).toFixed(1),
          right: +((xmax + 1) / 2 * rect.width).toFixed(1),
          top: +((1 - ymax) / 2 * rect.height).toFixed(1),
          bottom: +((1 - ymin) / 2 * rect.height).toFixed(1),
          w: +rect.width.toFixed(1),
          h: +rect.height.toFixed(1),
        },
        camera: { y: +camera.position.y.toFixed(3), z: +camera.position.z.toFixed(3), fov: camera.fov },
        scale: +assets.scale.toFixed(4),
        footOffset: +assets.footOffset.toFixed(3),
        muscles: assets.muscleMeshes,
      };
    };
    window.__mb3d = {
      select: (k) => onSelect?.(k),
      clear: () => onSelect?.(null),
      info: () => ({ muscles: assets.muscleMeshes, groups: GROUPS.length, hits: assets.hitMeshes.length }),
      metrics,
      pick: (fx, fy) => {
        const rect = gl.domElement.getBoundingClientRect();
        const ndc = new THREE.Vector2(fx * 2 - 1, -(fy * 2 - 1));
        raycaster.setFromCamera(ndc, camera);
        const hits = raycaster.intersectObjects(assets.pickMeshes, false);
        return hits.slice(0, 8).map((h) => ({
          name: h.object.userData?.name || h.object.name,
          group: h.object.userData.group || null,
          d: +h.distance.toFixed(3),
          rect: [Math.round(rect.width), Math.round(rect.height)],
        }));
      },
    };
    return () => { delete window.__mb3d; };
  }, [assets, gl, camera, onSelect, raycaster]);

  // тап = выбор мышцы (raycast по реальным мешам), перетаскивание — вращение
  useEffect(() => {
    const el = gl.domElement;
    let down = null;
    const onDown = (e) => { down = { x: e.clientX, y: e.clientY }; };
    const onUp = (e) => {
      if (!down) return;
      const dist = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      down = null;
      if (dist > 9) return;
      const rect = el.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1
      );
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(assets.pickMeshes, false);
      if (!hits.length) {
        onSelect?.(null);
        return;
      }
      const first = hits[0];
      if (first.object.userData.group) {
        onSelect?.(first.object.userData.group);
        return;
      }
      // попали в кость/хрящ — берём мышцу не глубже 9 см под ней
      const behind = hits.find(
        (h) => h.object.userData.group && h.distance - first.distance < 0.09
      );
      onSelect?.(behind ? behind.object.userData.group : null);
    };
    let last = 0;
    const onMove = (e) => {
      if (!onHover || e.pointerType === "touch") return;
      const now = performance.now();
      if (now - last < 90) return;
      last = now;
      const rect = el.getBoundingClientRect();
      raycaster.setFromCamera(
        new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1
        ),
        camera
      );
      const hits = raycaster.intersectObjects(assets.pickMeshes, false);
      const hit = hits.find((h) => h.object.userData.group);
      onHover(hit ? hit.object.userData.group : null);
    };
    const onLeave = () => onHover?.(null);
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [gl, camera, raycaster, assets, onSelect, onHover]);

  return (
    <group scale={assets.scale} position={[0, -assets.footOffset, 0]} dispose={null}>
      <primitive object={assets.scene} />
    </group>
  );
}

function Rig({ ctl, targetY, children }) {
  const g = useRef(null);
  useFrame((_, dt) => {
    const c = ctl.current;
    const k = c.reduce ? 1 : Math.min(1, dt * 7.5);
    c.az += (c.azT - c.az) * k;
    c.polar += (c.polarT - c.polar) * k;
    c.zoom += (c.zoomT - c.zoom) * k;
    if (g.current) {
      g.current.rotation.y = c.az;
      g.current.rotation.x = c.polar;
      g.current.scale.setScalar(c.zoom);
    }
  });
  return (
    <group ref={g} position={[0, targetY, 0]}>
      <group position={[0, -targetY, 0]}>{children}</group>
    </group>
  );
}

function CameraRig({ assets }) {
  const { camera, size } = useThree();
  useEffect(() => {
    const fov = THREE.MathUtils.degToRad(camera.fov || FOV);
    const aspect = Math.max(0.25, size.width / Math.max(1, size.height));
    const worldH = BODY_HEIGHT;
    const worldW = Math.max(0.45, (assets.size?.x || 0.6) * assets.scale);
    const distV = worldH / 0.84 / 2 / Math.tan(fov / 2);
    const distH = (worldW * 1.55) / 2 / (Math.tan(fov / 2) * aspect);
    const dist = Math.max(distV, distH);
    const cy = worldH / 2;
    camera.position.set(0, cy, dist);
    camera.lookAt(0, cy, 0);
    camera.updateProjectionMatrix();
  }, [assets, camera, size.width, size.height]);
  return null;
}

function Ground() {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.001, 0]} receiveShadow>
      <planeGeometry args={[6, 6]} />
      <shadowMaterial transparent opacity={0.34} />
    </mesh>
  );
}

/* ------------------------------------------------------------------ */
/* публичный компонент                                                */
/* ------------------------------------------------------------------ */

export default function MuscleBody3D({
  regions = {},
  selected = null,
  onSelect,
  onFail,
  view = "front",
  testPrefix = "mm3d",
}) {
  const { status, progress, assets } = useEcorche();
  const ctl = useRef({
    az: 0,
    azT: 0,
    polar: 0,
    polarT: 0,
    zoom: 1,
    zoomT: 1,
    interacted: false,
    reduce: false,
  });
  const [hover, setHoverState] = useState(null);
  const setHover = useCallback((k) => setHoverState((prev) => (prev === k ? prev : k)), []);
  const ptrs = useRef(new Map());
  const pinch = useRef(0);
  const stageRef = useRef(null);
  const [visible, setVisible] = useState(true);

  const ready = status === "ready" && !!assets;
  const targetY = ready ? assets.centerY : BODY_HEIGHT / 2;
  const camZ = useMemo(() => (BODY_HEIGHT * 0.6) / Math.tan((FOV * Math.PI) / 360), []);

  useEffect(() => {
    if (status === "error") onFail?.();
  }, [status, onFail]);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (mq) ctl.current.reduce = !!mq.matches;
  }, []);

  const firstView = useRef(true);
  useEffect(() => {
    if (!ready) return;
    if (firstView.current) {
      firstView.current = false;
      return;
    }
    const c = ctl.current;
    c.interacted = true;
    c.azT = view === "back" ? Math.PI : 0;
    c.polarT = 0;
  }, [view, ready]);

  // пауза рендера вне экрана
  useEffect(() => {
    const el = stageRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver((es) => setVisible(es.some((e) => e.isIntersecting)), {
      threshold: 0,
      rootMargin: "80px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const onPointerDown = (e) => {
    ptrs.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    ctl.current.interacted = true;
    if (ptrs.current.size === 2) {
      const [a, b] = [...ptrs.current.values()];
      pinch.current = Math.hypot(a.x - b.x, a.y - b.y);
    }
  };

  const onPointerMove = (e) => {
    const prev = ptrs.current.get(e.pointerId);
    if (!prev) return;
    ptrs.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const c = ctl.current;
    if (ptrs.current.size >= 2) {
      const [a, b] = [...ptrs.current.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinch.current > 0 && d > 0) {
        c.zoomT = THREE.MathUtils.clamp(c.zoomT * (d / pinch.current), 0.8, 1.9);
      }
      pinch.current = d;
      return;
    }
    c.azT += (e.clientX - prev.x) * 0.009;
    c.polarT = THREE.MathUtils.clamp(c.polarT + (e.clientY - prev.y) * 0.004, -0.3, 0.3);
  };

  const onPointerUp = (e) => {
    ptrs.current.delete(e.pointerId);
    if (ptrs.current.size < 2) pinch.current = 0;
  };

  const onWheel = (e) => {
    e.preventDefault();
    const c = ctl.current;
    c.interacted = true;
    c.zoomT = THREE.MathUtils.clamp(c.zoomT * (1 - e.deltaY * 0.0015), 0.8, 1.9);
  };

  const topLabels = useMemo(() => {
    return Object.entries(regions || {})
      .filter(([, v]) => (v?.working_sets || 0) > 0)
      .sort((a, b) => (b[1].intensity_0_1 || 0) - (a[1].intensity_0_1 || 0))
      .slice(0, 4)
      .map(([k]) => muscleLabel(k))
      .join(", ");
  }, [regions]);

  return (
    <div className="mb3d" data-testid={`${testPrefix}-wrap`}>
      <div
        className="mb3d-stage"
        ref={stageRef}
        role="img"
        aria-label={`3D-карта мышц${topLabels ? `: сильнее всего проработаны ${topLabels}` : ""}. Вращайте фигуру, нажимайте на мышцы.`}
        data-testid={`${testPrefix}-stage`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerLeave={onPointerUp}
        onWheel={onWheel}
      >
        {ready ? (
          <Canvas
            frameloop={visible ? "always" : "never"}
            dpr={[1, 1.5]}
            shadows
            gl={{
              antialias: true,
              alpha: true,
              powerPreference: "high-performance",
              toneMapping: THREE.ACESFilmicToneMapping,
              toneMappingExposure: 1.05,
            }}
            camera={{ position: [0, targetY, camZ], fov: FOV, near: 0.05, far: 40 }}
            style={{ touchAction: "none" }}
          >
            <Environment />
            <ambientLight intensity={0.34} />
            <hemisphereLight args={["#dfe8ff", "#1b1410", 0.5]} />
            <directionalLight
              position={[2.2, 4.4, 3.0]}
              intensity={2.1}
              color="#fff3e4"
              castShadow
              shadow-mapSize-width={1024}
              shadow-mapSize-height={1024}
              shadow-camera-near={0.5}
              shadow-camera-far={12}
              shadow-camera-left={-0.9}
              shadow-camera-right={0.9}
              shadow-camera-top={2.1}
              shadow-camera-bottom={-0.3}
              shadow-bias={-0.0012}
            />
            <directionalLight position={[-2.6, 1.8, -2.0]} intensity={1.0} color="#8fb4ff" />
            <pointLight position={[0, 1.2, -2.4]} intensity={7} distance={6} color="#ff9640" />
            <CameraRig assets={assets} />
            <Rig ctl={ctl} targetY={targetY}>
              <Model
                assets={assets}
                regions={regions}
                selected={selected}
                onSelect={onSelect}
                onHover={setHover}
              />
              <Ground />
            </Rig>
          </Canvas>
        ) : (
          <div className="mb3d-progress" data-testid={`${testPrefix}-loading`}>
            <div className="mb3d-progress-bar">
              <i style={{ width: `${Math.max(6, Math.round(progress * 100))}%` }} />
            </div>
            <span>
              {status === "error"
                ? "Не удалось загрузить модель"
                : `Загружаем 3D-модель… ${Math.round(progress * 100)}%`}
            </span>
          </div>
        )}
        <div className="mb3d-vignette" aria-hidden />
      </div>
      <div className="mb3d-hint" data-testid={`${testPrefix}-hint`}>
        {hover || selected ? (
          <span className="mb3d-hint-name">{muscleLabel(hover || selected)}</span>
        ) : (
          "Вращайте фигуру · нажмите на мышцу"
        )}
      </div>
    </div>
  );
}
