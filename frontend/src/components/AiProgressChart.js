import React, { useMemo, useState } from "react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import { TrendingUp } from "lucide-react";

const round1 = (v) => Math.round(v * 10) / 10;

function buildSeries(tpl) {
  const weeks = tpl?.weeks || [];
  if (weeks.length < 2) return null;
  const isPct = !!tpl.requires_maxes;
  const base = tpl.base_maxes || {};
  const perEx = new Map();
  weeks.forEach((w, i) => {
    (w.days || []).forEach((d) => {
      if (d.is_rest) return;
      (d.exercises || []).forEach((e) => {
        let top = 0;
        (e.sets_scheme || []).forEach((s) => {
          const v = parseFloat(s.weight);
          if (v > 0) top = Math.max(top, v);
        });
        if (!top || !e.exercise_name) return;
        if (!perEx.has(e.exercise_name)) {
          perEx.set(e.exercise_name, { name: e.exercise_name, lift: e.lift_group, vals: {} });
        }
        const rec = perEx.get(e.exercise_name);
        rec.vals[i] = Math.max(rec.vals[i] || 0, top);
      });
    });
  });
  const exList = [...perEx.values()].filter((r) => Object.keys(r.vals).length >= 2);
  if (!exList.length) return null;

  const toVal = (r, v) =>
    isPct && r.lift ? (v / (parseFloat(base[r.lift]) || 100)) * 100 : v;

  const overall = weeks.map((_, i) => {
    const rels = exList
      .map((r) => {
        const bIdx = Math.min(...Object.keys(r.vals).map(Number));
        const bVal = r.vals[bIdx];
        return r.vals[i] != null && bVal ? (r.vals[i] / bVal) * 100 : null;
      })
      .filter((x) => x != null);
    return {
      label: `Н${i + 1}`,
      value: rels.length ? round1(rels.reduce((a, b) => a + b, 0) / rels.length) : null,
    };
  });

  const byExercise = exList.map((r) => ({
    name: r.name,
    unit: isPct && r.lift ? "%1ПМ" : "кг",
    data: weeks.map((_, i) => ({
      label: `Н${i + 1}`,
      value: r.vals[i] != null ? round1(toVal(r, r.vals[i])) : null,
    })),
  }));

  const pts = overall.filter((p) => p.value != null);
  const peak = pts.length ? Math.max(...pts.map((p) => p.value)) : 0;
  const delta = pts.length >= 2 ? round1(peak - pts[0].value) : 0;
  return { overall, byExercise, delta };
}

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length || payload[0].value == null) return null;
  return (
    <div className="ai-chart-tip">
      <span>{label}</span>
      <b>{payload[0].value} {unit}</b>
    </div>
  );
}

export const AiProgressChart = ({ tpl }) => {
  const series = useMemo(() => buildSeries(tpl), [tpl]);
  const [sel, setSel] = useState(-1);
  if (!series) return null;
  const isOverall = sel < 0;
  const ex = isOverall ? null : series.byExercise[sel];
  const data = isOverall ? series.overall : ex.data;
  const unit = isOverall ? "%" : ex.unit;

  return (
    <div className="ai-charts" data-testid="ai-progress-charts">
      <div className="ai-charts-head">
        <span className="ai-charts-title"><TrendingUp size={15} /> Прогноз прогресса</span>
        {isOverall && series.delta !== 0 ? (
          <span className={`ai-charts-delta ${series.delta > 0 ? "up" : "down"}`}
            data-testid="ai-charts-delta">
            {series.delta > 0 ? "+" : ""}{series.delta}% к пику
          </span>
        ) : null}
      </div>
      <div className="ai-charts-chips">
        <button className={`ai-chip sm ${isOverall ? "active" : ""}`}
          onClick={() => setSel(-1)} data-testid="ai-chart-chip-overall">
          Общий (средний)
        </button>
        {series.byExercise.map((r, i) => (
          <button key={r.name} className={`ai-chip sm ${sel === i ? "active" : ""}`}
            onClick={() => setSel(i)} data-testid={`ai-chart-chip-${i}`}>
            {r.name}
          </button>
        ))}
      </div>
      <div className="ai-chart-box" data-testid="ai-chart-box">
        <ResponsiveContainer width="100%" height={170}>
          <AreaChart data={data} margin={{ top: 10, right: 8, left: -16, bottom: 0 }}>
            <defs>
              <linearGradient id="aiProgGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#FF8A24" stopOpacity={0.32} />
                <stop offset="100%" stopColor="#FF8A24" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="label" tick={{ fill: "rgba(255,255,255,0.45)", fontSize: 11 }}
              axisLine={false} tickLine={false} />
            <YAxis domain={["auto", "auto"]} tick={{ fill: "rgba(255,255,255,0.35)", fontSize: 10 }}
              axisLine={false} tickLine={false} width={44} />
            <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ stroke: "rgba(255,255,255,0.15)" }} />
            <Area type="monotone" dataKey="value" stroke="#FF8A24" strokeWidth={2}
              fill="url(#aiProgGrad)" connectNulls
              dot={{ r: 3, fill: "#FF8A24", strokeWidth: 0 }}
              isAnimationActive animationDuration={900} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="ai-charts-note">
        {isOverall
          ? "Средний рост топ-веса по всем упражнениям, неделя 1 = 100%"
          : `Топ-вес рабочего подхода по неделям, ${unit}`}
      </p>
    </div>
  );
};
