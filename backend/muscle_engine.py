"""ИИ-разбор мышц после тренировки: строгий JSON-контракт + правила.

Идея
----
После завершения тренировки сессия превращается в компактный «паспорт нагрузки»
(упражнения, подходы, вес, повторы, %1ПМ), который:

1. прогоняется через детерминированный движок правил (`build_rules`) — он всегда
   доступен и даёт стабильный результат без внешних сервисов;
2. при наличии ключа ИИ отдаётся языковой модели (`refine_with_ai`), которая
   уточняет интенсивности и добавляет человеческие пояснения — но НЕ может
   выйти за пределы контракта: неизвестные мышцы отбрасываются, значения
   зажимаются в [0,1], отклонение от базовых значений ограничено.

Оба пути возвращают один и тот же JSON (`CONTRACT_VERSION`), поэтому фронтенд
подсвечивает мышцы одинаково — меняется только точность и наличие пояснений.

Контракт muscle_load_v1
-----------------------
{
  "version": "muscle_load_v1",
  "engine": "rules" | "ai",
  "model": str | null,
  "created_at": ISO8601,
  "session_id": str,
  "summary": str,                 # 1–2 предложения по-русски
  "focus": [muscle, ...],         # до 3 главных мышц
  "muscles": {
     <muscle>: {
        "load_0_1": float,        # 0..1 — чем красить на 3D-модели
        "sets": int,              # эффективные подходы
        "hard_sets": int,         # подходы с интенсивностью >= 0.7
        "mechanical_kg": int,     # вклад тоннажа
        "role": "primary" | "secondary" | "stabilizer" | "none",
        "why": str                # короткое пояснение
     }
  },
  "totals": {"volume_kg": int, "hard_sets": int, "muscles_trained": int},
  "balance": {"over": [muscle...], "under": [muscle...]},
  "warnings": [str, ...]
}
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from seed import normalize_muscle_weights

CONTRACT_VERSION = "muscle_load_v1"

MUSCLES: Tuple[str, ...] = (
    "chest", "upper_back", "lats", "traps", "front_delts", "side_delts",
    "rear_delts", "biceps", "triceps", "forearms", "abs", "obliques",
    "lower_back", "glutes", "quads", "hamstrings", "adductors", "abductors",
    "calves", "neck",
)

MUSCLE_LABELS: Dict[str, str] = {
    "chest": "Грудные",
    "upper_back": "Верх спины",
    "lats": "Широчайшие",
    "traps": "Трапеции",
    "front_delts": "Передние дельты",
    "side_delts": "Средние дельты",
    "rear_delts": "Задние дельты",
    "biceps": "Бицепсы",
    "triceps": "Трицепсы",
    "forearms": "Предплечья",
    "abs": "Пресс",
    "obliques": "Косые",
    "lower_back": "Поясница",
    "glutes": "Ягодицы",
    "quads": "Квадрицепсы",
    "hamstrings": "Бицепс бедра",
    "adductors": "Приводящие",
    "abductors": "Отводящие",
    "calves": "Икры",
    "neck": "Шея",
}

# Антагонисты: если одна половина пары «перегружена», вторая — кандидат в отстающие.
ANTAGONISTS: Dict[str, Tuple[str, ...]] = {
    "chest": ("upper_back", "lats"),
    "upper_back": ("chest",),
    "lats": ("chest",),
    "quads": ("hamstrings", "glutes"),
    "hamstrings": ("quads",),
    "glutes": ("quads",),
    "biceps": ("triceps",),
    "triceps": ("biceps",),
    "abs": ("lower_back",),
    "lower_back": ("abs",),
    "front_delts": ("rear_delts",),
    "rear_delts": ("front_delts",),
    "adductors": ("abductors",),
    "abductors": ("adductors",),
}

# Сколько «условного веса» брать за подход в упражнениях с собственным весом.
BODYWEIGHT_DEFAULT_KG = 75.0
BODYWEIGHT_SHARE = 0.65

# Доля тоннажа (mechanical) и доля тяжёлых подходов (hard_sets) в итоговой нагрузке.
MECHANICAL_SHARE = 0.62
HARD_SET_SHARE = 0.38
# Гамма-коррекция: поднимает средние значения, чтобы подсветка читалась глазом.
LOAD_GAMMA = 0.75
HARD_SET_INTENSITY = 0.7


# ---------------------------------------------------------------------------
# интенсивность подхода
# ---------------------------------------------------------------------------
def intensity_from_percent(percent_1rm: Optional[float]) -> Optional[float]:
    """Интенсивность подхода по %1ПМ (линейно между опорными точками)."""
    if percent_1rm is None:
        return None
    try:
        p = float(percent_1rm)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    points = ((50, 0.30), (60, 0.52), (65, 0.62), (70, 0.72), (75, 0.82),
              (80, 0.90), (85, 0.95), (90, 1.00), (100, 1.00))
    if p <= points[0][0]:
        return points[0][1]
    for (p0, v0), (p1, v1) in zip(points, points[1:]):
        if p <= p1:
            return round(v0 + (v1 - v0) * (p - p0) / (p1 - p0), 3)
    return 1.0


def intensity_from_reps(reps: Optional[int]) -> float:
    """Интенсивность подхода по числу повторов (когда %1ПМ неизвестен)."""
    try:
        r = int(reps or 0)
    except (TypeError, ValueError):
        return 0.5
    if r <= 0:
        return 0.0
    if r <= 3:
        return 1.0
    if r <= 6:
        return 0.95
    if r <= 9:
        return 0.88
    if r <= 12:
        return 0.80
    if r <= 15:
        return 0.68
    if r <= 20:
        return 0.55
    return 0.42


def _norm_muscle_key(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    k = raw.strip().lower()
    return k if k in MUSCLES else None


# Слаги из планов, которых нет в справочнике упражнений: ближайший аналог.
SLUG_ALIASES: Dict[str, str] = {
    "squat-highbar": "back-squat",
    "bench-medium-grip": "bench-press",
    "seated-db-press": "overhead-press",
    "bench-competition": "bench-press",
    "deadlift-classic": "deadlift",
    "vertical-pulldown": "lat-pulldown",
    "squat-lowbar": "back-squat",
    "bench-board": "bench-press",
    "bench-pin": "bench-press",
    "deadlift-sumo": "deadlift",
    "romanian-dl": "romanian-deadlift",
    "ohp": "overhead-press",
    "pullups": "pull-up",
    "chinups": "pull-up",
    "bb-row": "barbell-row",
    "db-row": "dumbbell-row",
}

# Ключевые слова в названии упражнения (рус.) → группы, если справочник не помог.
NAME_RULES: Tuple[Tuple[str, List[str], List[str]], ...] = (
    (r"жим\s+лёжа|жим\s+лежа|жим\s+на\s+наклонн|жим\s+гантел", ["chest"], ["triceps", "shoulders"]),
    (r"жим\s+узким|француз|трицепс|разгибание\s+на\s+трицепс", ["triceps"], ["chest"]),
    (r"жим\s+(стоя|сидя|армейск)|жим\s+гантел\s+сидя|махи|разводк", ["shoulders"], ["triceps"]),
    (r"становая|румынск", ["back"], ["legs", "glutes", "core"]),
    (r"тяга\s+(верхн|блока|к\s+лицу)|подтяг|вертикальн", ["back"], ["biceps"]),
    (r"тяга", ["back"], ["biceps", "core"]),
    (r"присед|выпад|жим\s+ногами|разгибание\s+ног", ["legs"], ["glutes", "core"]),
    (r"сгибание\s+ног|бицепс\s+бедра", ["hamstrings"], ["glutes"]),
    (r"икр|носк", ["calves"], []),
    (r"бицепс|подъём\s+на\s+бицепс", ["biceps"], []),
    (r"планка|пресс|скручиван|подъём\s+ног", ["core"], []),
    (r"шраг", ["traps"], []),
    (r"отжим|брусь", ["chest"], ["triceps"]),
    (r"гиперэкстенз|наклон", ["core"], ["glutes"]),
)


def _def_from_name(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    for pattern, primary, secondary in NAME_RULES:
        if re.search(pattern, name, re.I):
            return {"name": name, "muscle_groups": primary,
                    "secondary_groups": secondary, "equipment": None, "_fallback": True}
    return None


def resolve_exercise(exercise: Dict[str, Any], ex_by_id, ex_by_slug) -> Dict[str, Any]:
    """Найти определение упражнения: справочник → алиас слага → разбор названия.

    Без этого шага упражнения из планов, которых нет в справочнике (например
    «Присед (с высокой штангой)»), выпадали из расчёта карты мышц целиком.
    """
    ex_def = None
    if exercise.get("exercise_id"):
        ex_def = ex_by_id.get(exercise["exercise_id"])
    slug = exercise.get("exercise_slug")
    if not ex_def and slug:
        ex_def = ex_by_slug.get(slug)
    if not ex_def and slug and slug in SLUG_ALIASES:
        ex_def = ex_by_slug.get(SLUG_ALIASES[slug])
    if not ex_def:
        ex_def = _def_from_name(exercise.get("exercise_name") or "")
    return ex_def or {}


# ---------------------------------------------------------------------------
# правила
# ---------------------------------------------------------------------------
def build_evidence(session: Dict[str, Any], ex_by_id, ex_by_slug,
                   bodyweight_kg: Optional[float] = None) -> Dict[str, Any]:
    """Компактный «паспорт нагрузки» сессии — вход и для правил, и для ИИ."""
    exercises: List[Dict[str, Any]] = []
    for ex in session.get("exercises") or []:
        if ex.get("status") != "done":
            continue
        ex_def = resolve_exercise(ex, ex_by_id, ex_by_slug)
        sets = []
        for lg in ex.get("set_logs") or []:
            if not lg.get("done"):
                continue
            weight = lg.get("weight")
            reps = lg.get("reps")
            if not reps:
                continue
            sets.append({
                "w": float(weight) if weight else 0.0,
                "reps": int(reps),
                "pct": lg.get("percent_1rm"),
            })
        if not sets:
            # legacy-сессии без set_logs: восстанавливаем по схеме подходов
            for sch in ex.get("sets_scheme") or []:
                reps = sch.get("reps")
                if not reps:
                    continue
                for _ in range(int(sch.get("sets") or 0)):
                    sets.append({
                        "w": float(sch.get("weight") or 0.0),
                        "reps": int(reps),
                        "pct": sch.get("percent_1rm"),
                    })
        if not sets:
            continue
        weights = normalize_muscle_weights(
            ex_def.get("muscle_groups") or [], ex_def.get("secondary_groups") or []
        )
        if not weights:
            continue
        exercises.append({
            "name": ex.get("exercise_name") or ex_def.get("name") or "",
            "weights": {m: round(w, 3) for m, w in weights.items()},
            "muscle_group": ex.get("muscle_group") or ex_def.get("muscle_groups", [None])[0]
            if isinstance(ex_def.get("muscle_groups"), list) and ex_def.get("muscle_groups")
            else ex.get("muscle_group"),
            "primary": [m for m in (ex_def.get("muscle_groups") or [])],
            "secondary": [m for m in (ex_def.get("secondary_groups") or [])],
            "equipment": ex_def.get("equipment"),
            "sets": sets,
        })
    return {
        "session_id": session.get("id"),
        "title": session.get("title"),
        "date": session.get("date"),
        "bodyweight_kg": bodyweight_kg or BODYWEIGHT_DEFAULT_KG,
        "exercises": exercises,
    }


def _set_effective_weight(weight: float, bodyweight_kg: float) -> float:
    """Вес штанги или условный вес тела для упражнений с собственным весом."""
    if weight and weight > 0:
        return weight
    return bodyweight_kg * BODYWEIGHT_SHARE


def build_rules(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Детерминированный разбор: без ИИ, всегда доступен.

    Возвращает JSON контракта muscle_load_v1 (engine="rules").
    """
    bodyweight = float(evidence.get("bodyweight_kg") or BODYWEIGHT_DEFAULT_KG)
    stats: Dict[str, Dict[str, float]] = {
        m: {"mechanical": 0.0, "sets": 0.0, "hard": 0.0} for m in MUSCLES
    }
    role: Dict[str, str] = {m: "none" for m in MUSCLES}
    per_exercise: List[Dict[str, Any]] = []
    total_volume = 0.0
    total_hard = 0.0

    for ex in evidence.get("exercises") or []:
        dist = {m: float(w) for m, w in (ex.get("weights") or {}).items() if m in MUSCLES}
        if not dist:
            continue
        ex_mech = 0.0
        ex_sets = 0.0
        ex_hard = 0.0
        for s in ex.get("sets") or []:
            eff_w = _set_effective_weight(float(s.get("w") or 0.0), bodyweight)
            reps = int(s.get("reps") or 0)
            inten = intensity_from_percent(s.get("pct"))
            if inten is None:
                inten = intensity_from_reps(reps)
            if inten <= 0 or reps <= 0:
                continue
            load = eff_w * reps * inten
            ex_mech += load
            ex_sets += 1
            if inten >= HARD_SET_INTENSITY:
                ex_hard += 1
            total_volume += load
            for m, share in dist.items():
                st = stats[m]
                st["mechanical"] += load * share
                st["sets"] += share
                if inten >= HARD_SET_INTENSITY:
                    st["hard"] += share
                    total_hard += share
                if share >= 1.0:
                    role[m] = "primary"
                elif role[m] != "primary":
                    role[m] = "secondary"
        if ex_mech > 0:
            per_exercise.append({
                "name": ex.get("name"),
                "mechanical": round(ex_mech),
                "sets": int(ex_sets),
                "hard_sets": int(ex_hard),
                "muscles": {m: round(w, 2) for m, w in dist.items()},
            })

    max_mech = max((s["mechanical"] for s in stats.values()), default=0.0)
    max_hard = max((s["hard"] for s in stats.values()), default=0.0)

    muscles: Dict[str, Dict[str, Any]] = {}
    for m in MUSCLES:
        st = stats[m]
        n_mech = st["mechanical"] / max_mech if max_mech > 0 else 0.0
        n_hard = st["hard"] / max_hard if max_hard > 0 else 0.0
        raw = MECHANICAL_SHARE * n_mech + HARD_SET_SHARE * n_hard
        load = round(min(1.0, max(0.0, raw)) ** LOAD_GAMMA, 2) if raw > 0 else 0.0
        muscles[m] = {
            "load_0_1": load,
            "sets": int(round(st["sets"])),
            "hard_sets": int(round(st["hard"])),
            "mechanical_kg": round(st["mechanical"]),
            "role": role[m] if st["mechanical"] > 0 else "none",
            "why": _rule_why(m, st, role[m]),
        }

    focus = [m for m in sorted(MUSCLES, key=lambda k: -muscles[k]["load_0_1"])
             if muscles[m]["load_0_1"] >= 0.35][:3]

    over = [m for m in MUSCLES if muscles[m]["load_0_1"] >= 0.8 and muscles[m]["hard_sets"] >= 5]
    under: List[str] = []
    for m in over:
        for ant in ANTAGONISTS.get(m, ()):
            if muscles[ant]["load_0_1"] < 0.3 and ant not in under:
                under.append(ant)

    return {
        "version": CONTRACT_VERSION,
        "engine": "rules",
        "model": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session_id": evidence.get("session_id"),
        "summary": _rule_summary(focus, under),
        "focus": focus,
        "muscles": muscles,
        "totals": {
            "volume_kg": round(total_volume),
            "hard_sets": int(round(total_hard)),
            "muscles_trained": sum(1 for m in MUSCLES if muscles[m]["load_0_1"] > 0.05),
        },
        "balance": {"over": over, "under": under},
        "warnings": _rule_warnings(muscles, evidence),
        "exercises": per_exercise,
    }


def _rule_why(muscle: str, st: Dict[str, float], role: str) -> str:
    label = MUSCLE_LABELS.get(muscle, muscle)
    if st["mechanical"] <= 0:
        return "Без нагрузки в этой тренировке"
    kind = {"primary": "основная", "secondary": "дополнительная"}.get(role, "стабилизирующая")
    sets = int(round(st["sets"]))
    hard = int(round(st["hard"]))
    return f"{label}: {kind} нагрузка, {sets} подх. ({hard} тяжёлых)"


def _rule_summary(focus: List[str], under: List[str]) -> str:
    if not focus:
        return "Нагрузки по мышцам не зафиксировано"
    names = ", ".join(MUSCLE_LABELS.get(m, m).lower() for m in focus)
    text = f"Главная нагрузка: {names}."
    if under:
        miss = ", ".join(MUSCLE_LABELS.get(m, m).lower() for m in under[:3])
        text += f" Не затронуты: {miss}."
    return text


def _rule_warnings(muscles: Dict[str, Dict[str, Any]], evidence: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    trained = [m for m in MUSCLES if muscles[m]["load_0_1"] > 0.05]
    if not trained:
        return ["В тренировке не отмечено выполненных подходов"]
    push = {"chest", "front_delts", "triceps", "side_delts"}
    pull = {"upper_back", "lats", "rear_delts", "biceps"}
    if set(trained) & push and not set(trained) & pull:
        out.append("Только жимовая работа — нет тяговых упражнений")
    if set(trained) & pull and not set(trained) & push:
        out.append("Только тяговая работа — нет жимовых упражнений")
    if "quads" in trained and "hamstrings" not in trained:
        out.append("Квадрицепсы без бицепса бедра — добавьте сгибания ног")
    if "hamstrings" in trained and "quads" not in trained:
        out.append("Бицепс бедра без квадрицепсов — добавьте приседания или жим ногами")
    if "abs" not in trained and muscles["lower_back"]["load_0_1"] > 0.5:
        out.append("Поясница нагружена без работы на пресс")
    if muscles["calves"]["load_0_1"] == 0 and any(
        muscles[m]["load_0_1"] > 0.5 for m in ("quads", "hamstrings", "glutes")
    ):
        out.append("Икры не задействованы")
    return out


# ---------------------------------------------------------------------------
# валидация ответа ИИ
# ---------------------------------------------------------------------------
def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Достать JSON-объект из ответа модели (в т.ч. из ```json блока)."""
    if not text:
        return None
    import json
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    for candidate in (raw, raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else ""):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return None


def validate_ai_payload(data: Any, baseline: Dict[str, Any],
                        max_delta: float = 0.2) -> Optional[Dict[str, Any]]:
    """Строгая валидация ответа ИИ. Возвращает контракт или None (тогда — правила).

    Гарантии:
    * мышцы только из канона (лишние отбрасываются);
    * load_0_1 ∈ [0,1] и отличается от базового не более чем на `max_delta`
      (ИИ уточняет, а не переписывает);
    * строки обрезаны, списки ограничены.
    """
    if not isinstance(data, dict):
        return None
    raw_muscles = data.get("muscles")
    if not isinstance(raw_muscles, dict) or not raw_muscles:
        return None

    out = {
        "version": CONTRACT_VERSION,
        "engine": "ai",
        "model": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session_id": baseline.get("session_id"),
        "summary": "",
        "focus": [],
        "muscles": {},
        "totals": dict(baseline.get("totals") or {}),
        "balance": {"over": [], "under": []},
        "warnings": [],
        "exercises": baseline.get("exercises") or [],
    }

    base_muscles = baseline.get("muscles") or {}
    touched = 0
    for key, val in raw_muscles.items():
        m = _norm_muscle_key(key)
        if not m:
            continue
        base = base_muscles.get(m) or {}
        try:
            load = float(val.get("load_0_1"))
        except (TypeError, ValueError, AttributeError):
            load = float(base.get("load_0_1") or 0.0)
        base_load = float(base.get("load_0_1") or 0.0)
        load = max(base_load - max_delta, min(base_load + max_delta, load))
        load = max(0.0, min(1.0, load))
        why = str((val or {}).get("why") or base.get("why") or "").strip()[:120]
        out["muscles"][m] = {
            "load_0_1": round(load, 2),
            "sets": int(base.get("sets") or 0),
            "hard_sets": int(base.get("hard_sets") or 0),
            "mechanical_kg": int(base.get("mechanical_kg") or 0),
            "role": base.get("role") or "none",
            "why": why or base.get("why") or "",
        }
        touched += 1

    if touched == 0:
        return None
    # добиваем мышцы, которые ИИ не вернул, базовыми значениями
    for m in MUSCLES:
        if m not in out["muscles"]:
            out["muscles"][m] = dict(base_muscles.get(m) or {
                "load_0_1": 0.0, "sets": 0, "hard_sets": 0, "mechanical_kg": 0,
                "role": "none", "why": "",
            })

    focus = []
    for m in data.get("focus") or []:
        k = _norm_muscle_key(m)
        if k and k not in focus:
            focus.append(k)
    out["focus"] = focus[:3] or baseline.get("focus") or []

    summary = str(data.get("summary") or "").strip()[:400]
    out["summary"] = summary or baseline.get("summary") or ""

    warnings = []
    for w in data.get("warnings") or []:
        s = str(w).strip()[:160]
        if s and s not in warnings:
            warnings.append(s)
    out["warnings"] = warnings[:5]

    balance = data.get("balance") if isinstance(data.get("balance"), dict) else {}
    for side in ("over", "under"):
        vals = []
        for m in balance.get(side) or []:
            k = _norm_muscle_key(m)
            if k and k not in vals:
                vals.append(k)
        out["balance"][side] = vals[:6]
    return out


def ai_messages(evidence: Dict[str, Any], baseline: Dict[str, Any]) -> List[Dict[str, str]]:
    """Промпт: строгие правила + базовый разбор, который нужно уточнить."""
    import json
    muscles_list = "\n".join(f"- {m} — {MUSCLE_LABELS[m]}" for m in MUSCLES)
    system = f"""Ты — тренер-методист. По протоколу тренировки ты выставляешь нагрузку
на каждую мышцу для подсветки на анатомической карте.

ВЕРНИ ТОЛЬКО JSON, без пояснений вокруг:
{{
  "muscles": {{"<muscle>": {{"load_0_1": <число 0..1>, "why": "<до 90 символов, по-русски>"}}}},
  "summary": "<1-2 предложения по-русски>",
  "focus": ["<до 3 мышц>"],
  "balance": {{"over": ["<мышцы>"], "under": ["<мышцы>"]}},
  "warnings": ["<до 3 коротких предупреждений>"]
}}

ПРАВИЛА:
1. Ключи мышц — только из списка (латиницей, как есть):
{muscles_list}
2. load_0_1 — доля нагрузки на мышцу: 1.0 — максимум этой тренировки, 0 — не работала.
   Учитывай тоннаж (вес × повторы), число подходов и интенсивность (%1ПМ или повторы).
   Мышца, которая только стабилизирует, получает 0.1–0.3, а не 0.
3. Не меняй базовые значения больше чем на 0.2 — ты уточняешь расчёт, а не заменяешь его.
4. Включай в ответ ВСЕ мышцы, которые работали (load_0_1 > 0.05), и те, что заметно отстали.
5. "why" — конкретика: название упражнения и объём («жим лёжа 6×4 @77.5 кг»), без общих слов.
6. Никаких выдуманных мышц, упражнений и цифр: только данные протокола.
7. Русский язык, без эмодзи, без markdown."""

    user = (
        "Протокол тренировки:\n"
        + json.dumps(evidence, ensure_ascii=False)
        + "\n\nБазовый расчёт правилами (его нужно уточнить):\n"
        + json.dumps({
            "muscles": {m: {"load_0_1": v["load_0_1"], "sets": v["sets"],
                            "hard_sets": v["hard_sets"]}
                        for m, v in (baseline.get("muscles") or {}).items()},
            "focus": baseline.get("focus"),
            "totals": baseline.get("totals"),
        }, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def merge_ai_response(content: str, baseline: Dict[str, Any],
                      model: Optional[str]) -> Optional[Dict[str, Any]]:
    """Разобрать и провалидировать сырой ответ модели."""
    data = _extract_json_object(content)
    if not data:
        return None
    out = validate_ai_payload(data, baseline)
    if not out:
        return None
    out["model"] = model
    return out


def scale_for_map(load: float) -> float:
    """Единая кривая для подсветки (мягкий старт, читаемый максимум)."""
    try:
        v = float(load)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, math.sqrt(v))), 3)
