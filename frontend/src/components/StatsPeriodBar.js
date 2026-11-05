import React from "react";
import { PERIODS } from "@/lib/period";

export default function StatsPeriodBar({ period, setPeriod, compact = false }) {
  const shown = compact ? PERIODS.filter((p) => ["week", "month", "all"].includes(p.key)) : PERIODS;
  return (
    <div className="stats-scope" data-testid="stats-period-bar" role="tablist" aria-label="Период статистики">
      {shown.map((p) => (
        <button
          key={p.key}
          type="button"
          role="tab"
          aria-selected={period === p.key}
          className={`stats-scope-btn ${period === p.key ? "active" : ""}`}
          onClick={() => setPeriod(p.key)}
          data-testid={`period-btn-${p.key}`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}