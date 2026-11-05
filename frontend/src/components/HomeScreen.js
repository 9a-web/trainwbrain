import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, ChevronRight, Dumbbell, Sparkles, Users } from "lucide-react";
import { useUser } from "@/context/UserContext";
import { getCardioStats, getStats, getCoachClients } from "@/api";
import { useCapabilities } from "@/hooks/useCapabilities";
import DateSelector from "@/components/DateSelector";
import useBackgroundJobs from "@/hooks/useBackgroundJobs";
import { haptic } from "@/lib/platform";
import "@/App.css";

const pluralize = (n, forms) => {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
};

// Get greeting and icon based on current time
const getGreetingData = () => {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) {
    return { text: "Доброе утро", icon: "/sunrise.svg" };
  } else if (hour >= 12 && hour < 18) {
    return { text: "Добрый день", icon: "/day.svg" };
  } else if (hour >= 18 && hour < 23) {
    return { text: "Добрый вечер", icon: "/sunset.svg" };
  }
  return { text: "Доброй ночи", icon: "/night.svg" };
};

/**
 * Маршрут для возврата к фоновой задаче.
 * Задачи вида generate/refine/parse/parse-photo ведут на страницу ИИ.
 * diary-задачи ведут на /profile (дневник).
 */
function routeForBgJob(job) {
  const kind = job.kind || "";
  if (kind.startsWith("diary_")) {
    return "/profile";
  }
  if (kind === "cardio_parse") {
    return "/cardio";
  }
  return `/programs/ai?job=${encodeURIComponent(job.id)}`;
}

const avatarFor = (a) => {
  if (a?.picture) return a.picture;
  const name = encodeURIComponent(a?.first_name || "U");
  return `https://ui-avatars.com/api/?name=${name}&background=FF6B00&color=fff&size=80&bold=true`;
};

export default function HomeScreen({ readOnly = false, notice = null, showPlan = true }) {
  const { user, avatarUrl } = useUser();
  const navigate = useNavigate();
  const [streak, setStreak] = useState(0);
  const [cardio, setCardio] = useState(null);
  const { jobs, runningCount } = useBackgroundJobs();
  const { coachMode } = useCapabilities();

  // Режим тренера: список клиентов. Свои тренировки на главном экране не
  // показываются — вместо них тренировка выбранного клиента.
  const [coachClients, setCoachClients] = useState([]);
  const [clientsLoading, setClientsLoading] = useState(false);
  // Выбранный клиент: изначально никто не выбран — тогда вместо тренировки
  // показывается подсказка.
  const [selectedAid, setSelectedAid] = useState(null);

  useEffect(() => {
    if (!coachMode || !user?.telegram_id) {
      setCoachClients([]);
      setSelectedAid(null);
      return;
    }
    setClientsLoading(true);
    getCoachClients(user.telegram_id)
      .then((data) => {
        const list = data.clients || [];
        setCoachClients(list);
        // Список обновился — выбранный клиент мог исчезнуть.
        setSelectedAid((cur) =>
          cur && list.some((c) => c.athlete?.telegram_id === cur) ? cur : null
        );
      })
      .catch(() => setCoachClients([]))
      .finally(() => setClientsLoading(false));
  }, [coachMode, user?.telegram_id]);

  const selectedAthlete = useMemo(
    () => coachClients.find((c) => c.athlete?.telegram_id === selectedAid)?.athlete || null,
    [coachClients, selectedAid]
  );

  useEffect(() => {
    if (!user?.telegram_id) return undefined;
    let cancelled = false;
    const load = async () => {
      try {
        const s = await getStats(user.telegram_id);
        if (!cancelled) setStreak(s?.streak_days || 0);
      } catch (e) {
        /* no-op */
      }
    };
    load();
    const onProgress = () => load();
    window.addEventListener("twb:progress", onProgress);
    return () => {
      cancelled = true;
      window.removeEventListener("twb:progress", onProgress);
    };
  }, [user?.telegram_id]);

  // Виджет кардио: минуты за неделю + норма
  useEffect(() => {
    if (!user?.telegram_id) return undefined;
    let cancelled = false;
    getCardioStats(user.telegram_id, { period: "week" })
      .then((d) => { if (!cancelled) setCardio(d || null); })
      .catch(() => { if (!cancelled) setCardio(null); });
    return () => { cancelled = true; };
  }, [user?.telegram_id]);

  const greetingData = getGreetingData();

  return (
    <div className="app-container" data-testid="main-container">
      {/* Gradient Background with Blur Effect */}
      <div className="gradient-background" data-testid="gradient-background">
        <img
          src="/gradientcenter.png"
          alt=""
          aria-hidden="true"
        />
      </div>

      {/* Content Layer */}
      <div className="content-layer" data-testid="content-layer">
        {/* Header */}
        <header className="header" data-testid="header">
          {/* Logo */}
          <div className="header-logo" data-testid="header-logo">
            <img src="/TWBlogo.png" alt="TrainWithBrain" />
          </div>

          {/* Right side: Menu + Avatar (в клиентском режиме библиотека программ недоступна) */}
          <div className="header-right" data-testid="header-right">
            {!readOnly ? (
              <Link
                to="/programs"
                className="menu-button"
                data-testid="menu-button"
                aria-label="Программы"
              >
                <img src="/menu.svg" alt="Программы" width={40} height={40} />
              </Link>
            ) : null}
            {avatarUrl ? (
              <Link to="/profile" aria-label="Профиль" data-testid="profile-link">
                <img
                  src={avatarUrl}
                  alt="Профиль"
                  className="profile-avatar"
                  data-testid="profile-avatar"
                />
              </Link>
            ) : null}
          </div>
        </header>

        {/* Main Content Area */}
        <main className="main-content" data-testid="main-content">
          {notice ? <div className="home-screen-notice">{notice}</div> : null}

          <div className="greeting-row" data-testid="greeting-row">
            <h1 className="greeting-text" data-testid="greeting-text">
              {greetingData.text}, {user?.first_name || "Гость"}!
            </h1>
            <img
              src={greetingData.icon}
              alt=""
              className="greeting-icon"
              data-testid="greeting-icon"
            />
          </div>

          {/* Фоновые задачи ИИ — плашка с количеством активных процессов */}
          {jobs.length > 0 ? (
            <div className="bg-jobs-bar" data-testid="bg-jobs-bar">
              {jobs.map((job) => (
                <button
                  key={job.id}
                  type="button"
                  className={`bg-job-chip ${job.status === "running" ? "running" : job.status === "done" ? "done" : "error"}`}
                  onClick={() => navigate(routeForBgJob(job))}
                  aria-label={`Фоновая задача: ${job.preview || job.kind} (${job.status === "running" ? "выполняется" : job.status === "done" ? "готова" : "ошибка"})`}
                  data-testid={`bg-job-${job.id}`}
                >
                  <Sparkles size={14} />
                  <span className="bg-job-label">{job.preview || job.kind}</span>
                  <span className="bg-job-status">
                    {job.status === "running" ? "⋯" : job.status === "done" ? "✓" : "✗"}
                  </span>
                </button>
              ))}
              {runningCount > 0 ? (
                <span className="bg-jobs-count" data-testid="bg-jobs-count">
                  {runningCount} активн{runningCount === 1 ? "ая" : "ые"}
                </span>
              ) : null}
            </div>
          ) : null}

          {/* Training Streak — ведёт к экрану тренировочной серии.
              В режиме тренера главный экран — рабочее место: свои тренировки
              (серия, кардио, недельный план) здесь не показываются. */}
          {!coachMode ? (
            <button
              type="button"
              className="streak-row streak-row-link"
              data-testid="streak-row"
              onClick={() => navigate("/streak")}
              aria-label="Открыть тренировочную серию"
            >
              <img
                src="/fire_strike.svg"
                alt=""
                className="streak-icon"
                data-testid="streak-icon"
              />
              <span className="streak-text" data-testid="streak-text">
                Тренировочная серия в течение {streak} {pluralize(streak, ["дня", "дней", "дней"])}
              </span>
              <ChevronRight size={18} className="streak-chevron" aria-hidden="true" />
            </button>
          ) : null}

          {/* Кардио за неделю → экран кардио */}
          {!coachMode ? (
            <button
              type="button"
              className="cardio-widget"
              data-testid="home-cardio-widget"
              onClick={() => navigate("/cardio")}
              aria-label="Открыть кардио"
            >
              <span className="cardio-widget-ico" aria-hidden="true">
                <Activity size={17} />
              </span>
              <span className="cardio-widget-body">
                <span className="cardio-widget-top">
                  <b data-testid="home-cardio-minutes">
                    {cardio?.weekly_minutes || 0} мин
                  </b>
                  <span className="cardio-widget-sub">
                    {cardio?.weekly_target
                      ? `из ${cardio.weekly_target} мин · норма недели`
                      : "кардио за неделю"}
                  </span>
                </span>
                {cardio?.weekly_target ? (
                  <span className="cardio-widget-track">
                    <i
                      style={{
                        width: `${Math.min(
                          100,
                          Math.round(((cardio.weekly_minutes || 0) / cardio.weekly_target) * 100)
                        )}%`,
                      }}
                    />
                  </span>
                ) : (
                  <span className="cardio-widget-sub">
                    {(cardio?.sessions || 0) > 0
                      ? `${cardio.sessions} ${cardio.sessions === 1 ? "сессия" : "сессий"} · ${cardio.km || 0} км`
                      : "Добавьте первую запись"}
                  </span>
                )}
              </span>
              <ChevronRight size={18} className="streak-chevron" aria-hidden="true" />
            </button>
          ) : null}

          {/* Режим тренера: список клиентов в дизайне главного экрана.
              Тренировку выбранного клиента тренер заполняет ниже — в том же
              интерфейсе, что и свою (см. DateSelector coachMode). */}
          {coachMode ? (
            <div className="home-coach-clients" data-testid="home-coach-clients">
              <div className="home-coach-clients-label">
                <Users size={15} />
                <span>Клиенты{coachClients.length ? ` · ${coachClients.length}` : ""}</span>
              </div>
              {clientsLoading ? (
                <div className="home-coach-clients-loading">Загрузка…</div>
              ) : coachClients.length === 0 ? (
                <div className="home-coach-clients-empty" data-testid="home-coach-clients-empty">
                  <Dumbbell size={14} />
                  <span>Нет клиентов</span>
                </div>
              ) : (
                <div className="home-coach-avatar-scroll">
                  {coachClients.map((c) => {
                    const a = c.athlete || {};
                    const aid = a.telegram_id;
                    const isActive = selectedAid === aid;
                    return (
                      <button
                        key={aid}
                        type="button"
                        className={`home-coach-avatar-card ${isActive ? "is-active" : ""}`}
                        onClick={() => {
                          haptic("light");
                          // Повторное нажатие снимает выбор — снова «клиент не выбран».
                          setSelectedAid(isActive ? null : aid);
                        }}
                        aria-pressed={isActive}
                        data-testid={`home-coach-client-${aid}`}
                      >
                        <div className="home-coach-avatar-ring">
                          <img className="home-coach-avatar-img" src={avatarFor(a)} alt={a.first_name || "Клиент"} />
                        </div>
                        <span className="home-coach-avatar-name">{a.first_name || "Клиент"}</span>
                        {a.username ? <span className="home-coach-avatar-plan">@{a.username}</span> : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          ) : null}

          {/* План недели и тренировка: своя (спортсмен) или выбранного клиента
              (тренер). В режиме тренера интерфейс и дизайн — те же. */}
          {coachMode || showPlan ? (
            <DateSelector
              readOnly={readOnly}
              coachId={coachMode ? user?.telegram_id : null}
              athlete={coachMode ? selectedAthlete : null}
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}
