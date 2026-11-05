import React, { useState, useEffect, useMemo } from "react";
import { X, Search, ChevronRight, Dumbbell, ArrowLeft } from "lucide-react";
import { getExercises } from "@/api";
import "./ExercisePickerModal.css";

const MUSCLE_GROUPS = [
  "грудь", "спина", "плечи", "бицепс", "трицепс", "ноги", "ягодицы", "пресс", "предплечье", "трапеция",
];

const MUSCLE_ICONS = {
  грудь: "🏋️",
  спина: "🔙",
  плечи: "💪",
  бицепс: "💪",
  трицепс: "💪",
  ноги: "🦵",
  ягодицы: "🍑",
  пресс: "⚡",
  трапеция: "🔝",
  предплечье: "✊",
};

// Вариации упражнений: базовые сеты вариаций для популярных упражнений
const VARIATIONS = {
  "приседания": [
    { name: "Приседания со штангой", desc: "Классические приседания со штангой на спине", equipment: "Штанга" },
    { name: "Приседания в гакк-машине", desc: "Приседания в тренажёре Гаккеншмидта", equipment: "Тренажёр" },
    { name: "Приседания с гантелями", desc: "Приседания с гантелями в руках", equipment: "Гантели" },
    { name: "Приседания в Смите", desc: "Приседания в машине Смита", equipment: "Тренажёр" },
    { name: "Фронтальные приседания", desc: "Со штангой на груди (фронт-сквот)", equipment: "Штанга" },
    { name: "Болгарские сплит-приседания", desc: "Одна нога на возвышении", equipment: "Гантели/Штанга" },
  ],
  "жим": [
    { name: "Жим штанги лёжа", desc: "Классический жим на горизонтальной скамье", equipment: "Штанга" },
    { name: "Жим гантелей лёжа", desc: "Жим гантелями на горизонтальной скамье", equipment: "Гантели" },
    { name: "Жим в Смите", desc: "Жим в машине Смита", equipment: "Тренажёр" },
    { name: "Жим на наклонной скамье", desc: "Жим штанги на скамье 30-45°", equipment: "Штанга" },
    { name: "Жим гантелей на наклонной", desc: "Жим гантелями под углом", equipment: "Гантели" },
  ],
  "тяга": [
    { name: "Тяга штанги в наклоне", desc: "Классическая тяга штанги к поясу", equipment: "Штанга" },
    { name: "Тяга гантели в наклоне", desc: "Тяга гантели одной рукой", equipment: "Гантели" },
    { name: "Тяга Т-штанги", desc: "Тяга Т-грифа в наклоне", equipment: "Тренажёр" },
    { name: "Тяга верхнего блока", desc: "Тяга вертикального блока к груди", equipment: "Блок" },
    { name: "Тяга горизонтального блока", desc: "Тяга блока к поясу сидя", equipment: "Блок" },
  ],
  "подтягивания": [
    { name: "Подтягивания широким хватом", desc: "Классические подтягивания", equipment: "Перекладина" },
    { name: "Подтягивания обратным хватом", desc: "Подтягивания ладонями к себе", equipment: "Перекладина" },
    { name: "Подтягивания узким хватом", desc: "Подтягивания с узкой постановкой рук", equipment: "Перекладина" },
    { name: "Подтягивания с отягощением", desc: "Подтягивания с дополнительным весом", equipment: "Пояс/жилет" },
  ],
};

// Извлекаем ключевое слово для поиска вариаций
const getVariationKey = (name) => {
  const n = (name || "").toLowerCase();
  const keys = Object.keys(VARIATIONS);
  for (const k of keys) {
    if (n.includes(k)) return k;
  }
  return null;
};

const ExercisePickerModal = ({ onSelect, onClose }) => {
  const [catalog, setCatalog] = useState([]);
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [showVariations, setShowVariations] = useState(null); // exercise that has variations
  const [pickedExercise, setPickedExercise] = useState(null); // final selected exercise

  // Load catalog
  useEffect(() => {
    getExercises()
      .then((list) => setCatalog(list || []))
      .catch(() => {});
  }, []);

  // Unique muscle groups from catalog
  const availableGroups = useMemo(() => {
    const groups = new Set();
    (catalog || []).forEach((ex) => {
      (ex.muscle_groups || []).forEach((g) => {
        const gLower = (g || "").trim().toLowerCase();
        if (gLower) groups.add(gLower);
      });
    });
    return [...groups].sort();
  }, [catalog]);

  // Filtered exercises
  const filtered = useMemo(() => {
    let list = catalog || [];
    // Search filter
    if ((search || "").trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((ex) => (ex.name || "").toLowerCase().includes(q));
    }
    // Category filter
    if (selectedCategory) {
      list = list.filter((ex) =>
        (ex.muscle_groups || []).some((g) => (g || "").trim().toLowerCase() === selectedCategory)
      );
    }
    return list;
  }, [catalog, search, selectedCategory]);

  const handleSelect = (ex) => {
    const varKey = getVariationKey(ex.name || "");
    if (varKey && VARIATIONS[varKey]) {
      // Show variations first
      setShowVariations(ex);
    } else {
      // Select directly
      onSelect({
        name: ex.name,
        slug: ex.slug,
        muscle_group: (ex.muscle_groups || [])[0] || null,
      });
    }
  };

  const handleVariationSelect = (variation) => {
    onSelect({
      name: variation.name,
      slug: null,
      muscle_group: null,
    });
  };

  const handleDirectSelect = (ex) => {
    onSelect({
      name: ex.name,
      slug: ex.slug,
      muscle_group: (ex.muscle_groups || [])[0] || null,
    });
  };

  // Show variations panel
  if (showVariations) {
    const varKey = getVariationKey(showVariations.name || "");
    const vars = VARIATIONS[varKey] || [];
    return (
      <div className="ep-overlay" onClick={onClose} data-testid="ep-overlay">
        <div className="ep-modal" onClick={(e) => e.stopPropagation()}>
          <div className="ep-grabber" />

          <div className="ep-head" data-testid="ep-variations-head">
            <button
              className="ep-close"
              onClick={() => setShowVariations(null)}
              style={{ width: 38, height: 38, borderRadius: 10 }}
              aria-label="Назад"
            >
              <ArrowLeft size={18} />
            </button>
            <h3>Вариации</h3>
            <button className="ep-close" onClick={onClose} aria-label="Закрыть">
              <X size={18} />
            </button>
          </div>

          <div className="ep-list">
            <div
              className="ep-item selected"
              onClick={() => handleDirectSelect(showVariations)}
              data-testid="ep-var-original"
            >
              <div className="ep-item-icon">
                <Dumbbell size={16} />
              </div>
              <div className="ep-item-info">
                <span className="ep-item-name">{showVariations.name}</span>
                <span className="ep-item-meta">Исходное упражнение</span>
              </div>
              <ChevronRight size={16} className="ep-item-chevron" />
            </div>

            <div style={{ padding: "10px 0", textAlign: "center", color: "rgba(255,255,255,0.35)", fontSize: 12 }}>
              или выберите вариацию
            </div>

            {vars.map((v, i) => (
              <div
                key={i}
                className="ep-item"
                onClick={() => handleVariationSelect(v)}
                data-testid={`ep-var-${i}`}
              >
                <div className="ep-item-icon">
                  <Dumbbell size={16} />
                </div>
                <div className="ep-item-info">
                  <span className="ep-item-name">{v.name}</span>
                  <span className="ep-item-meta">{v.desc}</span>
                  <div className="ep-item-muscle">
                    <span>{v.equipment}</span>
                  </div>
                </div>
                <ChevronRight size={16} className="ep-item-chevron" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ep-overlay" onClick={onClose} data-testid="ep-overlay">
      <div className="ep-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Выбор упражнения">
        <div className="ep-grabber" aria-hidden="true" />

        <div className="ep-head" data-testid="ep-head">
          <h3>Выбрать упражнение</h3>
          <button className="ep-close" onClick={onClose} aria-label="Закрыть" data-testid="ep-close">
            <X size={18} />
          </button>
        </div>

        <div className="ep-search-wrap" style={{ position: "relative" }}>
          <Search size={17} className="ep-search-icon" aria-hidden="true" />
          <input
            className="ep-search"
            type="text"
            placeholder="Поиск упражнения…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
            data-testid="ep-search"
          />
        </div>

        {/* Category chips */}
        <div className="ep-cats" data-testid="ep-cats" role="tablist">
          <button
            className={`ep-cat ${selectedCategory === null ? "active" : ""}`}
            onClick={() => setSelectedCategory(null)}
            role="tab"
            aria-selected={selectedCategory === null}
            data-testid="ep-cat-all"
          >
            Все
          </button>
          {availableGroups.map((group) => (
            <button
              key={group}
              className={`ep-cat ${selectedCategory === group ? "active" : ""}`}
              onClick={() => setSelectedCategory(selectedCategory === group ? null : group)}
              role="tab"
              aria-selected={selectedCategory === group}
              data-testid={`ep-cat-${group}`}
            >
              {(MUSCLE_ICONS[group] || "")} {group.charAt(0).toUpperCase() + group.slice(1)}
            </button>
          ))}
        </div>

        {/* Exercise list */}
        <div className="ep-list" data-testid="ep-list">
          {filtered.length === 0 ? (
            <div className="ep-empty">
              {search ? "Ничего не найдено" : "Упражнения не загружены"}
            </div>
          ) : (
            filtered.slice(0, 100).map((ex) => {
              const muscles = (ex.muscle_groups || []).slice(0, 3);
              const hasVariations = !!getVariationKey(ex.name || "");
              return (
                <div
                  key={ex.id || ex.slug}
                  className="ep-item"
                  onClick={() => handleSelect(ex)}
                  data-testid={`ep-item-${ex.slug || ex.id}`}
                >
                  <div className="ep-item-icon">
                    <Dumbbell size={16} />
                  </div>
                  <div className="ep-item-info">
                    <span className="ep-item-name">{ex.name}</span>
                    {muscles.length > 0 ? (
                      <div className="ep-item-muscle">
                        {muscles.map((m) => (
                          <span key={m}>{m}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  {hasVariations ? (
                    <span style={{ fontSize: 10, color: "rgba(255,255,255,0.35)", marginRight: 4 }}>
                      вар.
                    </span>
                  ) : null}
                  <ChevronRight size={16} className="ep-item-chevron" />
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};

export default ExercisePickerModal;