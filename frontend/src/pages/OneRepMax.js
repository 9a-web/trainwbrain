import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Calculator } from "lucide-react";
import { useBackButton } from "@/hooks/useTelegramUI";
import { haptic } from "@/lib/platform";

const C = {
  bg: "#1C1C1C",
  card: "#333333",
  accent: "#FF6B00",
  muted: "#959595",
  text: "#FFFFFF",
  line: "rgba(255,255,255,0.08)",
};

const num = (v) => {
  const n = Number(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : 0;
};

// Формулы оценки 1ПМ по рабочему подходу
const formulas = (w, r) => {
  if (w <= 0 || r <= 0) return [];
  const res = [
    { name: "Epley", value: w * (1 + r / 30) },
    { name: "Lombardi", value: w * Math.pow(r, 0.10) },
    { name: "Lander", value: (100 * w) / (101.3 - 2.67123 * r) },
  ];
  if (r < 37) res.push({ name: "Brzycki", value: (w * 36) / (37 - r) });
  return res.filter((x) => Number.isFinite(x.value) && x.value > 0);
};

const PERCENTS = [100, 95, 90, 85, 80, 75, 70, 65, 60];

export default function OneRepMax() {
  const navigate = useNavigate();
  useBackButton(true, () => navigate(-1));

  const [weight, setWeight] = useState("");
  const [reps, setReps] = useState("");

  const w = num(weight);
  const r = Math.round(num(reps));
  const rows = useMemo(() => formulas(w, r), [w, r]);
  const estimate = rows.length
    ? rows.reduce((s, x) => s + x.value, 0) / rows.length
    : 0;

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text, padding: "16px 16px 48px" }} data-testid="one-rm-page">
      <header style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <button
          onClick={() => navigate(-1)}
          aria-label="Назад"
          data-testid="one-rm-back"
          style={{ background: "transparent", border: "none", color: C.text, cursor: "pointer", padding: 4 }}
        >
          <ArrowLeft size={22} />
        </button>
        <h1 style={{ fontSize: 20, margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <Calculator size={20} color={C.accent} /> Калькулятор 1ПМ
        </h1>
      </header>

      <div style={{ background: C.card, borderRadius: 16, padding: 16, marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 12 }}>
          <label style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontSize: 13, color: C.muted }}>Рабочий вес, кг</span>
            <input
              type="number"
              inputMode="decimal"
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
              placeholder="80"
              data-testid="one-rm-weight"
              style={inputStyle}
            />
          </label>
          <label style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontSize: 13, color: C.muted }}>Повторы</span>
            <input
              type="number"
              inputMode="numeric"
              value={reps}
              onChange={(e) => setReps(e.target.value)}
              placeholder="5"
              data-testid="one-rm-reps"
              style={inputStyle}
            />
          </label>
        </div>
        <p style={{ color: C.muted, fontSize: 12, margin: "10px 0 0" }}>
          Формулы точны для 1–10 повторов. Вводите результат рабочего подхода «почти до отказа».
        </p>
      </div>

      {estimate > 0 ? (
        <>
          <div
            style={{
              background: "linear-gradient(-34deg, #FF8A24, #FFDA24)",
              color: "#1C1C1C",
              borderRadius: 16,
              padding: 20,
              textAlign: "center",
              marginBottom: 16,
            }}
            data-testid="one-rm-result"
          >
            <div style={{ fontSize: 13, fontWeight: 600, opacity: 0.75 }}>Оценочный 1ПМ</div>
            <div style={{ fontSize: 44, fontWeight: 800, lineHeight: 1.1 }}>
              {estimate.toFixed(1)} кг
            </div>
          </div>

          <Section title="По формулам">
            {rows.map((x) => (
              <Row key={x.name} label={x.name} value={`${x.value.toFixed(1)} кг`} />
            ))}
          </Section>

          <Section title="Рабочие веса от 1ПМ">
            {PERCENTS.map((p) => (
              <Row key={p} label={`${p}%`} value={`${((estimate * p) / 100).toFixed(1)} кг`} />
            ))}
          </Section>
        </>
      ) : (
        <p style={{ color: C.muted, textAlign: "center", marginTop: 24 }}>
          Введите вес и повторы, чтобы увидеть расчёт.
        </p>
      )}
    </div>
  );
}

const inputStyle = {
  background: "#242424",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 10,
  color: "#fff",
  padding: "10px 12px",
  fontSize: 16,
  outline: "none",
  width: "100%",
};

function Section({ title, children }) {
  return (
    <div style={{ background: C.card, borderRadius: 16, padding: 16, marginBottom: 16 }}>
      <div style={{ fontSize: 13, color: C.muted, marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "8px 0",
        borderBottom: `1px solid ${C.line}`,
        fontSize: 15,
      }}
    >
      <span style={{ color: C.muted }}>{label}</span>
      <b>{value}</b>
    </div>
  );
}
