import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Bell, Clock, Trophy, UserCheck, Moon, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { useUser } from "@/context/UserContext";
import { haptic } from "@/lib/platform";
import { useBackButton } from "@/hooks/useTelegramUI";
import api from "@/api";
import "./NotificationSettings.css";

export default function NotificationSettings() {
  const { dbUser } = useUser();
  const navigate = useNavigate();
  useBackButton(true, () => navigate("/"));

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState({
    workout_reminders: true,
    time_before_workout_minutes: 60,
    report_reminders: true,
    report_reminder_time: "20:00",
    achievement_notifications: true,
    coach_notifications: true,
    quiet_hours_enabled: false,
    quiet_hours_start: "22:00",
    quiet_hours_end: "08:00",
  });

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get("/notifications/settings");
      setSettings((prev) => ({ ...prev, ...response.data }));
    } catch (e) {
      toast.error("Не удалось загрузить настройки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const saveSettings = async () => {
    setSaving(true);
    haptic("medium");
    try {
      await api.patch("/notifications/settings", settings);
      toast.success("Настройки сохранены");
    } catch (e) {
      toast.error("Не удалось сохранить настройки");
    } finally {
      setSaving(false);
    }
  };

  const sendTestNotification = async () => {
    haptic("light");
    try {
      await api.post("/notifications/test");
      toast.success("Тестовое уведомление отправлено");
    } catch (e) {
      toast.error("Не удалось отправить тестовое уведомление");
    }
  };

  const updateSetting = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  // В активном режиме «спортсмен» показываем уведомления от тренера.
  // (Раньше было user?.role, которого в объекте пользователя не существует.)
  const isClient = (dbUser?.active_mode || "athlete") !== "coach";

  if (loading) {
    return (
      <div className="notif-page">
        <div className="notif-loading">Загрузка...</div>
      </div>
    );
  }

  return (
    <div className="notif-page">
      <div className="notif-header">
        <button className="notif-back" onClick={() => navigate("/")} aria-label="Назад">
          <ArrowLeft size={20} />
        </button>
        <h1 className="notif-title">Уведомления</h1>
      </div>

      {/* Напоминания о тренировках */}
      <div className="notif-section">
        <div className="notif-section-header">
          <Bell size={20} className="notif-section-icon" />
          <div className="notif-section-title">Тренировки</div>
        </div>

        <div className="notif-card">
          <div className="notif-toggle-row">
            <div className="notif-toggle-info">
              <div className="notif-toggle-label">Напоминания о тренировках</div>
              <div className="notif-toggle-desc">Получать уведомления перед началом</div>
            </div>
            <label className="notif-switch">
              <input
                type="checkbox"
                checked={settings.workout_reminders}
                onChange={(e) => {
                  haptic("light");
                  updateSetting("workout_reminders", e.target.checked);
                }}
              />
              <span className="notif-switch-slider"></span>
            </label>
          </div>

          {settings.workout_reminders && (
            <div className="notif-slider-block">
              <div className="notif-slider-header">
                <Clock size={16} />
                <span>За {settings.time_before_workout_minutes} минут до тренировки</span>
              </div>
              <input
                type="range"
                min="30"
                max="180"
                step="15"
                value={settings.time_before_workout_minutes}
                onChange={(e) => {
                  haptic("light");
                  updateSetting("time_before_workout_minutes", parseInt(e.target.value));
                }}
                className="notif-slider"
              />
              <div className="notif-slider-labels">
                <span>30 мин</span>
                <span>180 мин</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Отчеты */}
      <div className="notif-section">
        <div className="notif-section-header">
          <Clock size={20} className="notif-section-icon" />
          <div className="notif-section-title">Отчеты</div>
        </div>

        <div className="notif-card">
          <div className="notif-toggle-row">
            <div className="notif-toggle-info">
              <div className="notif-toggle-label">Напоминания о заполнении отчетов</div>
              <div className="notif-toggle-desc">Ежедневное напоминание</div>
            </div>
            <label className="notif-switch">
              <input
                type="checkbox"
                checked={settings.report_reminders}
                onChange={(e) => {
                  haptic("light");
                  updateSetting("report_reminders", e.target.checked);
                }}
              />
              <span className="notif-switch-slider"></span>
            </label>
          </div>

          {settings.report_reminders && (
            <div className="notif-time-block">
              <div className="notif-time-label">Время напоминания</div>
              <input
                type="time"
                value={settings.report_reminder_time}
                onChange={(e) => {
                  haptic("light");
                  updateSetting("report_reminder_time", e.target.value);
                }}
                className="notif-time-input"
              />
            </div>
          )}
        </div>
      </div>

      {/* Достижения и тренер */}
      <div className="notif-section">
        <div className="notif-section-header">
          <Trophy size={20} className="notif-section-icon" />
          <div className="notif-section-title">Прогресс</div>
        </div>

        <div className="notif-card">
          <div className="notif-toggle-row">
            <div className="notif-toggle-info">
              <div className="notif-toggle-label">Уведомления о достижениях</div>
              <div className="notif-toggle-desc">Новые рекорды и достижения</div>
            </div>
            <label className="notif-switch">
              <input
                type="checkbox"
                checked={settings.achievement_notifications}
                onChange={(e) => {
                  haptic("light");
                  updateSetting("achievement_notifications", e.target.checked);
                }}
              />
              <span className="notif-switch-slider"></span>
            </label>
          </div>

          {isClient && (
            <div className="notif-toggle-row notif-toggle-row-border">
              <div className="notif-toggle-info">
                <div className="notif-toggle-label">Уведомления от тренера</div>
                <div className="notif-toggle-desc">Сообщения и комментарии</div>
              </div>
              <label className="notif-switch">
                <input
                  type="checkbox"
                  checked={settings.coach_notifications}
                  onChange={(e) => {
                    haptic("light");
                    updateSetting("coach_notifications", e.target.checked);
                  }}
                />
                <span className="notif-switch-slider"></span>
              </label>
            </div>
          )}
        </div>
      </div>

      {/* Тихие часы */}
      <div className="notif-section">
        <div className="notif-section-header">
          <Moon size={20} className="notif-section-icon" />
          <div className="notif-section-title">Тихие часы</div>
        </div>

        <div className="notif-card">
          <div className="notif-toggle-row">
            <div className="notif-toggle-info">
              <div className="notif-toggle-label">Не беспокоить</div>
              <div className="notif-toggle-desc">Отключить уведомления на ночь</div>
            </div>
            <label className="notif-switch">
              <input
                type="checkbox"
                checked={settings.quiet_hours_enabled}
                onChange={(e) => {
                  haptic("light");
                  updateSetting("quiet_hours_enabled", e.target.checked);
                }}
              />
              <span className="notif-switch-slider"></span>
            </label>
          </div>

          {settings.quiet_hours_enabled && (
            <div className="notif-quiet-times">
              <div className="notif-quiet-time">
                <div className="notif-time-label">Начало</div>
                <input
                  type="time"
                  value={settings.quiet_hours_start}
                  onChange={(e) => {
                    haptic("light");
                    updateSetting("quiet_hours_start", e.target.value);
                  }}
                  className="notif-time-input"
                />
              </div>
              <div className="notif-quiet-separator">—</div>
              <div className="notif-quiet-time">
                <div className="notif-time-label">Конец</div>
                <input
                  type="time"
                  value={settings.quiet_hours_end}
                  onChange={(e) => {
                    haptic("light");
                    updateSetting("quiet_hours_end", e.target.value);
                  }}
                  className="notif-time-input"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Кнопки действий */}
      <div className="notif-actions">
        <button className="notif-test-btn" onClick={sendTestNotification}>
          <Volume2 size={18} />
          Тестовое уведомление
        </button>
        <button
          className="notif-save-btn"
          onClick={saveSettings}
          disabled={saving}
        >
          {saving ? "Сохранение..." : "Сохранить настройки"}
        </button>
      </div>
    </div>
  );
}
