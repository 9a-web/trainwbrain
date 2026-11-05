/**
 * Общие данные по мышечным группам: подписи и цветовая шкала.
 * Используется и 2D-картой (MuscleMap), и 3D-моделью (MuscleBody3D).
 */

export const MUSCLE_LABELS = {
  chest: "Грудные",
  upper_back: "Верх спины",
  lats: "Широчайшие",
  traps: "Трапеции",
  front_delts: "Передние дельты",
  side_delts: "Средние дельты",
  rear_delts: "Задние дельты",
  biceps: "Бицепс",
  triceps: "Трицепс",
  forearms: "Предплечья",
  abs: "Пресс",
  obliques: "Косые",
  lower_back: "Поясница",
  glutes: "Ягодицы",
  quads: "Квадрицепсы",
  hamstrings: "Бицепс бедра",
  adductors: "Приводящие",
  abductors: "Отводящие",
  calves: "Икры",
  neck: "Шея",
};

export const muscleLabel = (key) => MUSCLE_LABELS[key] || key;

/** Смесь «бренд-оранжевый → тёплый жёлтый» по интенсивности 0..1. */
export function heatColor(k, alpha = 1) {
  const t = Math.min(1, Math.max(0, Number(k) || 0));
  const c1 = [255, 107, 0];
  const c2 = [255, 218, 36];
  const mix = c1.map((v, i) => Math.round(v + (c2[i] - v) * t));
  return alpha >= 1 ? `rgb(${mix[0]},${mix[1]},${mix[2]})` : `rgba(${mix[0]},${mix[1]},${mix[2]},${alpha})`;
}

/** Цвет региона для 2D-силуэта (неактивные — почти прозрачные). */
export function regionFill(intensity) {
  const k = Number(intensity) || 0;
  if (k <= 0) return "rgba(255,255,255,0.07)";
  return heatColor(k, 0.42 + 0.55 * k);
}

/** Канонические мышцы (порядок как на бэкенде). */
export const MUSCLE_CANON = [
  "chest", "upper_back", "lats", "traps", "front_delts", "side_delts",
  "rear_delts", "biceps", "triceps", "forearms", "abs", "obliques",
  "lower_back", "glutes", "quads", "hamstrings", "adductors", "abductors",
  "calves", "neck",
];

/** Раскладка старых групп упражнений на канон (копия бэкендовой). */
const LEGACY_MUSCLE_MAP = {
  legs: { quads: 1.0, hamstrings: 0.6, glutes: 0.6 },
  back: { lats: 1.0, upper_back: 1.0 },
  shoulders: { front_delts: 1.0, side_delts: 1.0, rear_delts: 1.0 },
  core: { abs: 1.0, obliques: 0.6 },
};

const CANON_MAP = { ...Object.fromEntries(MUSCLE_CANON.map((m) => [m, { [m]: 1.0 }])), ...LEGACY_MUSCLE_MAP };

/**
 * Веса мышц упражнения — те же правила, что и normalize_muscle_weights на
 * бэкенде: основные группы получают 1.0, вспомогательные 0.5.
 */
export function normalizeMuscleWeights(primary = [], secondary = []) {
  const out = {};
  const add = (groups, factor) => {
    (groups || []).forEach((g) => {
      Object.entries(CANON_MAP[g] || {}).forEach(([canon, w]) => {
        out[canon] = (out[canon] || 0) + w * factor;
      });
    });
  };
  add(primary, 1.0);
  add(secondary, 0.5);
  return out;
}
