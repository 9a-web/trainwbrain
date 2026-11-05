import React, { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, Loader2, LogOut } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useBackButton } from "@/hooks/useTelegramUI";
import HomeScreen from "@/components/HomeScreen";
import "./ClientDashboard.css";

/**
 * Главный экран в режиме «Клиент».
 *
 * Это ровно тот же главный экран, что видит тренер (HomeScreen): приветствие,
 * тренировочная серия, кардио за неделю и недельный план с тренировками.
 * Отличие одно — read-only: нет доступа к библиотеке программ, к запуску
 * тренировки и к редактированию плана.
 */
export default function ClientDashboard() {
  const { switchMode } = useAuth();
  const { capabilities, can } = useCapabilities();
  const navigate = useNavigate();
  const [leavingPreview, setLeavingPreview] = useState(false);

  // Пока capabilities не загрузились, считаем экран клиентским (без прав на
  // редактирование), чтобы кнопка «Начать» не мелькала до ответа бэкенда.
  const managed = capabilities?.access_tier === "coach_managed";
  const clientPreview = capabilities?.active_mode === "client";
  const readOnly = !capabilities || managed || clientPreview;

  const exitPreview = useCallback(async () => {
    if (leavingPreview) return;
    setLeavingPreview(true);
    try {
      let previous = "athlete";
      try {
        previous = window.localStorage.getItem("twb:preview_return_mode") || "athlete";
        window.localStorage.removeItem("twb:preview_return_mode");
      } catch (e) {
        /* no-op */
      }
      if (previous === "client") previous = "athlete";
      await switchMode(previous);
      navigate("/", { replace: true });
    } catch (e) {
      setLeavingPreview(false);
    }
  }, [leavingPreview, switchMode, navigate]);

  useBackButton(clientPreview, exitPreview);

  const previewBar = clientPreview ? (
    <section className="client-preview-bar" data-testid="client-preview-bar">
      <div>
        <Eye size={16} />
        <span>
          <b>Предпросмотр клиента</b> — так интерфейс видит ваш клиент. Показаны
          данные вашего аккаунта.
        </span>
      </div>
      <button
        type="button"
        onClick={exitPreview}
        disabled={leavingPreview}
        data-testid="exit-client-preview"
      >
        {leavingPreview ? <Loader2 size={14} className="twb-spin" /> : <LogOut size={14} />} Выйти
      </button>
    </section>
  ) : null;

  return (
    <HomeScreen
      readOnly={readOnly}
      showPlan={can("view_strength")}
      notice={previewBar}
    />
  );
}
