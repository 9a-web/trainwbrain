import React from "react";
import { Switch } from "@/components/ui/switch";
import "@/components/PermissionsMatrix.css";

// §2.3 — канонический список прав с русскими подписями.
export const PERMISSIONS = [
  { key: "log_strength", label: "Заполнять силовые" },
  { key: "log_cardio", label: "Заполнять кардио" },
  { key: "log_nutrition", label: "Заполнять питание" },
  { key: "view_strength", label: "Просмотр силовых" },
  { key: "view_muscle_map", label: "Просмотр карты мышц" },
  { key: "view_cardio", label: "Просмотр кардио" },
  { key: "view_nutrition", label: "Просмотр питания" },
  { key: "view_forecast", label: "Просмотр прогноза" },
  { key: "view_goals", label: "Просмотр целей" },
  { key: "manage_plan", label: "Редактировать план" },
  { key: "ai_programs", label: "ИИ-генерация программ" },
];

export const DEFAULT_PERMISSIONS = PERMISSIONS.reduce((acc, p) => {
  acc[p.key] = false;
  return acc;
}, {});

/**
 * Управляемая матрица прав (controlled). value — объект { key: bool }.
 * onChange(next) вызывается с новым объектом.
 */
export default function PermissionsMatrix({ value, onChange, disabled = false }) {
  const current = value || {};
  const setOne = (key, checked) => {
    if (!onChange) return;
    onChange({ ...current, [key]: checked });
  };

  return (
    <div className="perm-matrix" data-testid="permissions-matrix">
      {PERMISSIONS.map((p) => {
        const id = `perm-${p.key}`;
        return (
          <label
            key={p.key}
            className={`perm-row ${disabled ? "is-disabled" : ""}`}
            htmlFor={id}
            data-testid={`perm-row-${p.key}`}
          >
            <span className="perm-label">{p.label}</span>
            <Switch
              id={id}
              className="pm-switch"
              checked={!!current[p.key]}
              onCheckedChange={(checked) => setOne(p.key, checked)}
              disabled={disabled}
              data-testid={`perm-toggle-${p.key}`}
            />
          </label>
        );
      })}
    </div>
  );
}
