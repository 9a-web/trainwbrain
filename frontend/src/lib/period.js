// Единые константы периодов статистики.
// Совпадают с backend STATS_PERIOD_KEYS.
export const PERIODS = [
  { key: "week", label: "Неделя" },
  { key: "month", label: "Месяц" },
  { key: "quarter", label: "Квартал" },
  { key: "year", label: "Год" },
  { key: "all", label: "Всё время" },
];

export const PERIOD_MAP = Object.fromEntries(PERIODS.map((p) => [p.key, p.label]));
export const DEFAULT_PERIOD = "week";