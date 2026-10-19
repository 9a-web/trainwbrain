import React, { useState, useEffect } from "react";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from "recharts";
import { getMuscleGroupsStats, getCoachClientMuscleGroups } from "@/api";

// Маппинг групп мышц на русские названия
const MUSCLE_NAMES = {
  chest: "Грудь",
  back: "Спина",
  legs: "Ноги",
  shoulders: "Плечи",
  biceps: "Бицепс",
  triceps: "Трицепс",
  core: "Кор",
  glutes: "Ягодицы",
  hamstrings: "Бицепс бедра",
  quads: "Квадрицепс",
  calves: "Икры",
  lats: "Широчайшие"
};

// Цвета для мышечных групп
const MUSCLE_COLORS = {
  chest: "#FF8A24",
  back: "#36C5F0",
  legs: "#34D399",
  shoulders: "#FFDA24",
  biceps: "#A78BFA",
  triceps: "#FB7185",
  core: "#FCD34D",
  glutes: "#10B981",
  hamstrings: "#6EE7B7",
  quads: "#A7F3D0",
  calves: "#D1FAE5",
  lats: "#7DD3FC"
};

function ChartTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const data = payload[0].payload;
  return (
    <div className="stats-tt">
      <div className="stats-tt-label">{data.muscle}</div>
      <div className="stats-tt-row">
        <span className="stats-tt-name">Объём</span>
        <b className="stats-tt-val">{data.volume.toLocaleString("ru-RU")} кг</b>
      </div>
      <div className="stats-tt-row">
        <span className="stats-tt-name">Тренировок</span>
        <b className="stats-tt-val">{data.sessions}</b>
      </div>
    </div>
  );
}

export default function MuscleGroupsChart({ telegramId, coachId, period = "week" }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedPeriod, setSelectedPeriod] = useState(period);

  useEffect(() => {
    let alive = true;
    setLoading(true);

    const fetchData = coachId
      ? getCoachClientMuscleGroups(coachId, telegramId, { period: selectedPeriod })
      : getMuscleGroupsStats(telegramId, { period: selectedPeriod });

    fetchData
      .then((response) => {
        if (!alive) return;

        // Преобразуем данные для RadarChart
        const chartData = Object.entries(response.muscle_groups || {}).map(([key, stats]) => ({
          muscle: MUSCLE_NAMES[key] || key,
          volume: stats.volume,
          sessions: stats.sessions,
          key: key
        }));

        // Сортируем по объёму
        chartData.sort((a, b) => b.volume - a.volume);

        setData({
          ...response,
          chartData
        });
      })
      .catch(() => {
        if (alive) setData(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => { alive = false; };
  }, [telegramId, coachId, selectedPeriod]);

  if (loading) {
    return (
      <div className="stats-card">
        <div className="stats-card-head">
          <h3 className="stats-card-title">Карта нагрузки</h3>
        </div>
        <div style={{ padding: "40px", textAlign: "center", color: "rgba(255,255,255,0.5)" }}>
          Загрузка...
        </div>
      </div>
    );
  }

  if (!data || !data.chartData || data.chartData.length === 0) {
    return (
      <div className="stats-card">
        <div className="stats-card-head">
          <h3 className="stats-card-title">Карта нагрузки</h3>
        </div>
        <div style={{ padding: "40px", textAlign: "center", color: "rgba(255,255,255,0.5)" }}>
          Нет данных за выбранный период
        </div>
      </div>
    );
  }

  const maxVolume = Math.max(...data.chartData.map(d => d.volume));

  return (
    <div className="stats-card" data-testid="muscle-groups-chart">
      <div className="stats-card-head">
        <h3 className="stats-card-title">Карта нагрузки</h3>
        <div className="stats-chips-row">
          <button
            className={`stats-tab-chip ${selectedPeriod === "week" ? "active" : ""}`}
            onClick={() => setSelectedPeriod("week")}
            data-testid="period-week"
          >
            Неделя
          </button>
          <button
            className={`stats-tab-chip ${selectedPeriod === "month" ? "active" : ""}`}
            onClick={() => setSelectedPeriod("month")}
            data-testid="period-month"
          >
            Месяц
          </button>
          <button
            className={`stats-tab-chip ${selectedPeriod === "all" ? "active" : ""}`}
            onClick={() => setSelectedPeriod("all")}
            data-testid="period-all"
          >
            Всё время
          </button>
        </div>
      </div>

      <div style={{ marginTop: "20px" }}>
        <ResponsiveContainer width="100%" height={320}>
          <RadarChart data={data.chartData}>
            <PolarGrid stroke="rgba(255,255,255,0.1)" />
            <PolarAngleAxis
              dataKey="muscle"
              tick={{ fill: "rgba(255,255,255,0.7)", fontSize: 12 }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, maxVolume]}
              tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 10 }}
              tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}т` : v)}
            />
            <Radar
              name="Объём"
              dataKey="volume"
              stroke="#FF8A24"
              fill="#FF8A24"
              fillOpacity={0.5}
              strokeWidth={2}
            />
            <Tooltip content={<ChartTooltip />} />
          </RadarChart>
        </ResponsiveContainer>

        {/* Легенда с детальной информацией */}
        <div style={{ marginTop: "20px" }}>
          <ul className="stats-legend">
            {data.chartData.map((item) => {
              const color = MUSCLE_COLORS[item.key] || "#999";
              const pct = maxVolume > 0 ? Math.round((item.volume / maxVolume) * 100) : 0;
              return (
                <li key={item.key} data-testid={`muscle-${item.key}`}>
                  <div className="stats-legend-top">
                    <span className="stats-legend-dot" style={{ background: color }} />
                    <span className="stats-legend-name">{item.muscle}</span>
                    <b className="stats-legend-val">{item.volume.toLocaleString("ru-RU")} кг</b>
                    <span className="stats-legend-pct">{item.sessions} трен.</span>
                  </div>
                  <div className="stats-legend-bar">
                    <i style={{ width: `${pct}%`, background: color }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
