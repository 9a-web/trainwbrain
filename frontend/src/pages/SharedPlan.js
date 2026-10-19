import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Dumbbell, Loader2 } from "lucide-react";
import { getSharedPlanByToken } from "@/api";

const C = {
  bg: "#1C1C1C",
  card: "#333333",
  accent: "#FF6B00",
  muted: "#959595",
  text: "#FFFFFF",
  line: "rgba(255,255,255,0.08)",
};

const schemeText = (ex) => {
  const scheme = ex.sets_scheme || [];
  if (scheme.length) {
    return scheme
      .map((s) => {
        const w = s.weight != null && s.weight !== "" ? `${s.weight} кг` : "—";
        return `${s.sets}×${s.reps} @ ${w}`;
      })
      .join("  ·  ");
  }
  const w = ex.target_weight != null ? ` @ ${ex.target_weight} кг` : "";
  return `${ex.target_sets || "?"}×${ex.target_reps || "?"}${w}`;
};

export default function SharedPlan() {
  const { token } = useParams();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const p = await getSharedPlanByToken(token);
        if (alive) setPlan(p);
      } catch (e) {
        if (alive) setError("Ссылка не найдена или отключена");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [token]);

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text, padding: "20px 16px 48px" }} data-testid="shared-plan-page">
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <Dumbbell size={22} color={C.accent} />
          <span style={{ fontSize: 13, color: C.muted }}>TrainWithBrain · программа</span>
        </div>

        {loading ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: C.muted }}>
            <Loader2 size={18} className="spin" /> Загрузка…
          </div>
        ) : error ? (
          <div style={{ background: C.card, borderRadius: 16, padding: 20 }} data-testid="shared-plan-error">
            {error}
          </div>
        ) : (
          <>
            <h1 style={{ fontSize: 24, margin: "0 0 20px" }} data-testid="shared-plan-name">
              {plan?.name || "Программа"}
            </h1>
            {(plan?.weeks || []).map((week) => (
              <div key={week.week_index} style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>
                  Неделя {week.week_index}
                </div>
                {(week.days || []).map((day) => {
                  if (day.is_rest) return null;
                  return (
                    <div
                      key={day.day_index}
                      style={{ background: C.card, borderRadius: 16, padding: 16, marginBottom: 10 }}
                    >
                      <div style={{ fontWeight: 600, marginBottom: 10 }}>
                        {day.title || `День ${day.day_index}`}
                      </div>
                      {(day.exercises || [])
                        .slice()
                        .sort((a, b) => (a.order || 0) - (b.order || 0))
                        .map((ex, i) => (
                          <div
                            key={i}
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              gap: 12,
                              padding: "7px 0",
                              borderTop: i ? `1px solid ${C.line}` : "none",
                              fontSize: 14,
                            }}
                          >
                            <span style={{ flex: 1 }}>{ex.exercise_name || ex.name || "Упражнение"}</span>
                            <span style={{ color: C.muted, whiteSpace: "nowrap" }}>{schemeText(ex)}</span>
                          </div>
                        ))}
                    </div>
                  );
                })}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
