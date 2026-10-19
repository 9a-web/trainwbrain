import React from "react";
import { Pencil, Trash2 } from "lucide-react";
import "./SupersetGroup.css";

const SUPERSET_LETTERS = ["A", "B", "C", "D", "E", "F"];

/**
 * Компонент для отображения группы упражнений в суперсете
 * @param {Object} props
 * @param {Array} props.exercises - массив упражнений в суперсете
 * @param {string} props.supersetId - ID суперсета
 * @param {Function} props.onEdit - callback для редактирования упражнения (exercise, index)
 * @param {Function} props.onDelete - callback для удаления упражнения (exercise, index)
 * @param {Function} props.formatSets - функция форматирования подходов
 * @param {boolean} props.editable - можно ли редактировать
 */
export default function SupersetGroup({
  exercises,
  supersetId,
  onEdit,
  onDelete,
  formatSets,
  editable = true,
}) {
  if (!exercises || exercises.length === 0) return null;

  // Определяем цвет бордера на основе первой буквы ID
  const colorIndex = (supersetId?.charCodeAt(supersetId.length - 1) || 0) % 6;
  const colors = ["#3B82F6", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981", "#EF4444"];
  const borderColor = colors[colorIndex];

  // Получаем отдых после суперсета (берем из последнего упражнения)
  const restAfterSuperset = exercises[exercises.length - 1]?.rest_after_superset;

  return (
    <div className="superset-group" style={{ borderLeftColor: borderColor }}>
      <div className="superset-header">
        <span className="superset-label">Суперсет</span>
        {restAfterSuperset && (
          <span className="superset-rest">Отдых после: {restAfterSuperset}с</span>
        )}
      </div>

      {exercises.map((ex, idx) => {
        const letter = SUPERSET_LETTERS[idx] || idx + 1;
        const isLast = idx === exercises.length - 1;

        return (
          <div key={idx} className="superset-exercise">
            <div className="superset-ex-content">
              <div className="superset-ex-letter" style={{ backgroundColor: borderColor }}>
                {letter}
              </div>
              <div className="superset-ex-info">
                <span className="superset-ex-name">{ex.exercise_name}</span>
                <span className="superset-ex-sets">{formatSets(ex)}</span>
              </div>
              {editable && (
                <div className="superset-ex-actions">
                  <button
                    className="superset-icon"
                    onClick={() => onEdit(ex, idx)}
                    aria-label="Изменить"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    className="superset-icon superset-icon-danger"
                    onClick={() => onDelete(ex, idx)}
                    aria-label="Удалить"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              )}
            </div>
            {!isLast && (
              <div className="superset-arrow">
                <div className="superset-arrow-line" style={{ backgroundColor: borderColor }} />
                <span className="superset-arrow-text">Без отдыха ↓</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
