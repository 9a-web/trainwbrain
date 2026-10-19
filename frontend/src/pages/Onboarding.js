import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound, Users, Dumbbell, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { redeemInvite } from "@/api";
import { haptic, hapticNotify } from "@/lib/platform";
import "@/pages/Onboarding.css";

const errText = (err) => {
  const status = err && err.response && err.response.status;
  const d = err && err.response && err.response.data && err.response.data.detail;
  const msg = typeof d === "string" ? d : "";
  const low = msg.toLowerCase();
  if (low.includes("expired") || low.includes("просроч")) return "Код просрочен.";
  if (low.includes("used") || low.includes("max") || low.includes("использован"))
    return "Этот код уже использован.";
  if (low.includes("revoked") || low.includes("отозван")) return "Код отозван администратором.";
  if (status === 404) return "Код не найден. Проверьте написание.";
  if (status === 400 || status === 422) return "Код неверный. Проверьте написание.";
  return msg || "Не удалось применить код. Попробуйте ещё раз.";
};

export default function Onboarding() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const apply = async (e) => {
    e.preventDefault();
    const value = code.trim().toUpperCase();
    if (!value || busy) return;
    setError("");
    setBusy(true);
    haptic("medium");
    try {
      const res = await redeemInvite(value);
      try {
        window.localStorage.setItem(
          "twb_capabilities",
          JSON.stringify(res || {})
        );
      } catch (err) {
        /* no-op */
      }
      hapticNotify("success");
      toast.success("Код применён. Добро пожаловать!");
      navigate("/", { replace: true });
    } catch (err) {
      setError(errText(err));
      hapticNotify("error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="onb-page" data-testid="onboarding-page">
      <div className="onb-gradient" aria-hidden="true">
        <img src="/gradientcenter.png" alt="" />
      </div>

      <div className="onb-card anim-fade-up">
        <img src="/TWBlogo.png" alt="TrainWithBrain" className="onb-logo" />
        <h1 className="onb-title">TrainWithBrain</h1>
        <p className="onb-subtitle">
          Вход в приложение — только по приглашению. Введите код, который дал
          тренер или администратор.
        </p>

        <div className="onb-paths">
          <div className="onb-path" data-testid="onb-path-managed">
            <span className="onb-path-ic onb-ic-managed">
              <Users size={18} />
            </span>
            <div>
              <b>С тренером</b>
              <span>
                Тренер ведёт силовые и план. Вы заполняете кардио и питание,
                видите отчёты.
              </span>
            </div>
          </div>
          <div className="onb-path" data-testid="onb-path-standalone">
            <span className="onb-path-ic onb-ic-standalone">
              <Dumbbell size={18} />
            </span>
            <div>
              <b>Самостоятельно</b>
              <span>
                Полный доступ: свои программы, план, силовые, кардио, питание и
                аналитика.
              </span>
            </div>
          </div>
        </div>

        <form className="onb-form" onSubmit={apply}>
          <div className="onb-input-wrap">
            <KeyRound size={18} className="onb-input-ic" />
            <input
              className="onb-input"
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="TWB-XXXXXX"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={20}
              data-testid="invite-code-input"
            />
          </div>

          {error ? (
            <div className="onb-error" data-testid="onboarding-error">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            className="onb-submit"
            disabled={busy || !code.trim()}
            data-testid="apply-code-btn"
          >
            {busy ? <Loader2 size={17} className="spin" /> : null}
            {busy ? "Проверяем…" : "Применить код"}
          </button>
        </form>

        <p className="onb-hint">
          Нет кода? Обратитесь к своему тренеру или администратору приложения.
        </p>
      </div>
    </div>
  );
}
