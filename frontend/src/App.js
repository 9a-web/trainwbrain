import "@/App.css";
import { useEffect, useState, useRef, lazy, Suspense } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { UserProvider } from "@/context/UserContext";
import { redeemInvite } from "@/api";
// Экран, который нужен сразу (или почти сразу), грузим синхронно:
// главный экран и вход должны появляться без сетевого «догруза» чанка.
import HomeScreen from "@/components/HomeScreen";
import Login from "@/pages/Login";
import Onboarding from "@/pages/Onboarding";
import ImportLanding from "@/pages/ImportLanding";
import { getStartParam } from "@/lib/platform";
import { useCapabilities } from "@/hooks/useCapabilities";
import { Check, Info, AlertTriangle, X, Loader2 } from "lucide-react";
import BgJobFloater from "@/components/BgJobFloater";
import ErrorBoundary from "@/components/ErrorBoundary";

// --- Code splitting ------------------------------------------------------
// Всё остальное — отдельными чанками. Без этого весь бандл (three.js,
// recharts, шейдеры, все страницы) весил ~2.3 МБ и парсился на телефоне
// несколько секунд: приложение «зависало» на старте, а поля ввода
// не реагировали на тапы (главный поток занят разбором JS).
const chunk = (loader) => lazy(() => loader().then((m) => ({ default: m.default || m })));

const Programs = chunk(() => import(/* webpackChunkName: "programs" */ "@/pages/Programs"));
const ProgramBuilder = chunk(() => import(/* webpackChunkName: "program-builder" */ "@/pages/ProgramBuilder"));
const AiImport = chunk(() => import(/* webpackChunkName: "ai-import" */ "@/pages/AiImport"));
const Profile = chunk(() => import(/* webpackChunkName: "profile" */ "@/pages/Profile"));
const Coach = chunk(() => import(/* webpackChunkName: "coach" */ "@/pages/Coach"));
const CoachClient = chunk(() => import(/* webpackChunkName: "coach" */ "@/pages/CoachClient"));
const CoachPlanEditor = chunk(() => import(/* webpackChunkName: "coach" */ "@/pages/CoachPlanEditor"));
const CoachLiveSession = chunk(() => import(/* webpackChunkName: "coach" */ "@/pages/CoachLiveSession"));
const CoachDiary = chunk(() => import(/* webpackChunkName: "coach" */ "@/pages/CoachDiary"));
const StreakPage = chunk(() => import(/* webpackChunkName: "streak" */ "@/pages/Streak"));
const NotificationSettings = chunk(() => import(/* webpackChunkName: "notifications" */ "@/pages/NotificationSettings"));
const OneRepMax = chunk(() => import(/* webpackChunkName: "onerepmax" */ "@/pages/OneRepMax"));
const SharedPlan = chunk(() => import(/* webpackChunkName: "shared-plan" */ "@/pages/SharedPlan"));
const Admin = chunk(() => import(/* webpackChunkName: "admin" */ "@/pages/Admin"));
const CardioPage = chunk(() => import(/* webpackChunkName: "cardio" */ "@/pages/Cardio"));
const ClientDashboard = chunk(() => import(/* webpackChunkName: "client-dashboard" */ "@/pages/ClientDashboard"));
const SessionDetail = chunk(() => import(/* webpackChunkName: "session-detail" */ "@/pages/SessionDetail"));
const StatsPage = lazy(() => import(/* webpackChunkName: "stats" */ "@/pages/Stats").then((m) => ({ default: m.StatsPage })));
const CoachClientStatsPage = lazy(() =>
  import(/* webpackChunkName: "stats" */ "@/pages/Stats").then((m) => ({ default: m.CoachClientStatsPage }))
);

const Home = () => <HomeScreen />;

/** Route guards для тренерских/админских экранов.
 *
 * Роль coach остаётся у аккаунта навсегда, поэтому одного `roles.includes`
 * мало: кабинет тренера доступен только при активном режиме «Тренер», а
 * админ-панель — только с ролью admin. Прямой переход по ссылке в другом
 * режиме уводит на главный экран.
 */
const CoachRoute = ({ allowed, children }) =>
  allowed ? children : <Navigate to="/" replace />;

const AdminRoute = ({ allowed, children }) =>
  allowed ? children : <Navigate to="/" replace />;

const SplashScreen = () => (
  <div className="app-splash" data-testid="app-splash">
    <img src="/TWBlogo.png" alt="TrainWithBrain" className="app-splash-logo" />
  </div>
);

/** Лёгкий фолбэк для догружаемого чанка: без полноэкранного сплэша,
 *  чтобы не «мигать» логотипом на каждый переход. */
const RouteFallback = () => (
  <div className="route-fallback" data-testid="route-fallback" aria-busy="true">
    <span className="route-fallback-spinner" />
  </div>
);

// Handles the Google OAuth redirect back to <origin>/auth/google?code=...
const GOOGLE_ERROR_KEY = "twb_google_error";
const GOOGLE_ERROR_TEXT = {
  access_denied: "Вход через Google отменён.",
  state_mismatch: "Не удалось проверить безопасность входа. Попробуйте ещё раз.",
  exchange_failed: "Не удалось войти через Google. Попробуйте ещё раз.",
};
const stashGoogleError = (key) => {
  try {
    window.sessionStorage.setItem(GOOGLE_ERROR_KEY, GOOGLE_ERROR_TEXT[key] || GOOGLE_ERROR_TEXT.exchange_failed);
  } catch (e) {
    /* no-op */
  }
};

const GoogleCallback = () => {
  const { handleGoogleCode, consumeGoogleState } = useAuth();
  const navigate = useNavigate();
  const ranRef = useRef(false);
  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const error = params.get("error");
    const state = params.get("state");
    (async () => {
      if (error) {
        stashGoogleError(error);
      } else if (code) {
        if (!consumeGoogleState(state)) {
          stashGoogleError("state_mismatch");
        } else {
          try {
            await handleGoogleCode(code);
          } catch (e) {
            stashGoogleError("exchange_failed");
          }
        }
      }
      navigate("/", { replace: true });
    })();
  }, [handleGoogleCode, consumeGoogleState, navigate]);
  return <SplashScreen />;
};

// Отложенный инвайт-код: гость вводит код на /welcome, затем регистрируется/
// входит на /login, и после успешного входа код применяется автоматически.
const PENDING_INVITE_KEY = "twb_pending_invite";
function getPendingInvite() {
  try {
    return window.localStorage.getItem(PENDING_INVITE_KEY);
  } catch (e) {
    return null;
  }
}
function setPendingInvite(code) {
  try {
    if (code) window.localStorage.setItem(PENDING_INVITE_KEY, code);
    else window.localStorage.removeItem(PENDING_INVITE_KEY);
  } catch (e) {
    /* no-op */
  }
}

const AppShell = () => {
  const { loading, isAuthenticated } = useAuth();
  const {
    capabilities,
    onboarded,
    loading: capsLoading,
    refresh: refreshCapabilities,
  } = useCapabilities();
  const capsRoles = capabilities?.roles || [];
  // Managed-клиент по правам ИЛИ предпросмотр клиентского интерфейса
  // (режим «Клиент» в профиле тренера — только UI, права не меняются).
  const isManagedClient = capabilities?.access_tier === "coach_managed" && !capsRoles.includes("coach");
  const isClientPreview = capabilities?.active_mode === "client";
  const isClientView = isManagedClient || isClientPreview;
  // Тренерские/админские экраны: кабинет тренера открывается только в режиме
  // тренера, админ-панель — только с ролью admin. Роль coach у аккаунта остаётся
  // навсегда, поэтому одного `roles.includes("coach")` недостаточно.
  const capsActiveMode = capabilities?.active_mode || "athlete";
  const canUseCoachCabinet =
    (capsRoles.includes("coach") || capsRoles.includes("admin")) && capsActiveMode === "coach";
  const isAdminUser = capsRoles.includes("admin");
  const location = useLocation();
  const navigate = useNavigate();
  const importHandledRef = useRef(false);
  const [redeeming, setRedeeming] = useState(false);

  // Отложенный импорт по ссылке/коду: после логина или из Telegram start_param
  useEffect(() => {
    if (!isAuthenticated || importHandledRef.current) return;
    let code = null;
    try {
      code = window.localStorage.getItem("twb_pending_import");
    } catch (e) {
      /* no-op */
    }
    if (!code) {
      const sp = getStartParam();
      if (sp && sp.startsWith("import_")) code = sp.slice(7).replace(/_/g, "-");
    }
    if (code) {
      importHandledRef.current = true;
      try {
        window.localStorage.removeItem("twb_pending_import");
      } catch (e) {
        /* no-op */
      }
      navigate(`/import/${code}`);
    }
  }, [isAuthenticated, navigate]);

  // Гостевой шаг «код → вход»: после входа применяем отложенный код и
  // снимаем онбординг-гейт. Если код неверный/просрочен — очищаем и отдаём на гейт.
  useEffect(() => {
    if (!isAuthenticated) return;
    const code = getPendingInvite();
    if (!code) return;
    let cancelled = false;
    setRedeeming(true);
    (async () => {
      try {
        const caps = await redeemInvite(code);
        if (!cancelled) {
          setPendingInvite(null);
          try {
            window.localStorage.setItem("twb_capabilities", JSON.stringify(caps || {}));
          } catch (e) {
            /* no-op */
          }
          await refreshCapabilities();
        }
      } catch (e) {
        if (!cancelled) setPendingInvite(null);
      } finally {
        if (!cancelled) setRedeeming(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, refreshCapabilities]);

  // Свежие capabilities после входа: иначе онбординг-гейт работал бы на устаревшем
  // «гостевом» ответе и не отражал актуальный onboarded.
  useEffect(() => {
    if (!isAuthenticated) return;
    refreshCapabilities();
  }, [isAuthenticated, refreshCapabilities]);

  // Фаза 1 — онбординг-гейт. Редиректим на /welcome ТОЛЬКО когда бэкенд явно
  // сообщил onboarded === false (строго false). Пока применяется отложенный код —
  // держим сплэш-экран, чтобы не мигнуть на /welcome.
  if (
    isAuthenticated &&
    !capsLoading &&
    onboarded === false &&
    location.pathname !== "/welcome"
  ) {
    if (redeeming) return <SplashScreen />;
    return <Navigate to="/welcome" replace />;
  }
  if (location.pathname === "/auth/google") return <GoogleCallback />;
  if (location.pathname === "/login") {
    if (isAuthenticated) return <Navigate to="/" replace />;
    return <Login />;
  }
  if (loading || redeeming) return <SplashScreen />;
  if (!isAuthenticated) {
    // Публичные страницы доступны без входа
    if (location.pathname.startsWith("/import/")) return <ImportLanding />;
    if (location.pathname.startsWith("/shared/")) {
      return (
        <Suspense fallback={<SplashScreen />}>
          <Routes>
            <Route path="/shared/plan/:token" element={<SharedPlan />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      );
    }
    // Инвайт-первая стратегия: гостя встречает экран «вход по коду».
    return <Onboarding />;
  }
  // Авторизован: пока не известен onboarded (после входа/редима) — сплэш,
  // чтобы гейт не «мигал» приложением, а потом увёз на /welcome.
  if (capsLoading) return <SplashScreen />;
  return (
    <UserProvider>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={isClientView ? <ClientDashboard /> : <Home />} />
        <Route path="/programs" element={isClientView ? <Navigate to="/" replace /> : <Programs />} />
        <Route path="/programs/builder/:templateId" element={isClientView ? <Navigate to="/" replace /> : <ProgramBuilder />} />
        <Route path="/programs/ai" element={isClientView ? <Navigate to="/" replace /> : <AiImport />} />
        <Route path="/import/:code" element={<ImportLanding />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/stats/session/:sessionId" element={<SessionDetail />} />
        <Route path="/cardio" element={<CardioPage />} />
        <Route path="/streak" element={<StreakPage />} />
        <Route path="/notifications" element={<NotificationSettings />} />
        <Route path="/tools/1rm" element={<OneRepMax />} />
        <Route path="/welcome" element={<Onboarding />} />
        <Route path="/admin" element={<AdminRoute allowed={isAdminUser}><Admin /></AdminRoute>} />
        <Route path="/shared/plan/:token" element={<SharedPlan />} />
        <Route path="/coach" element={<CoachRoute allowed={canUseCoachCabinet}><Coach /></CoachRoute>} />
        <Route path="/coach/:athleteId" element={<CoachRoute allowed={canUseCoachCabinet}><CoachClient /></CoachRoute>} />
        <Route path="/coach/:athleteId/live" element={<CoachRoute allowed={canUseCoachCabinet}><CoachLiveSession /></CoachRoute>} />
        <Route path="/coach/:athleteId/diary" element={<CoachRoute allowed={canUseCoachCabinet}><CoachDiary /></CoachRoute>} />
        <Route path="/coach/diary" element={<CoachRoute allowed={canUseCoachCabinet}><CoachDiary /></CoachRoute>} />
        <Route path="/coach/:athleteId/edit" element={<CoachRoute allowed={canUseCoachCabinet}><CoachPlanEditor /></CoachRoute>} />
        <Route path="/coach/:athleteId/stats" element={<CoachRoute allowed={canUseCoachCabinet}><CoachClientStatsPage /></CoachRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      {/* Плавающее уведомление о фоновых ИИ-задачах (на всех страницах) */}
      <BgJobFloater />
    </UserProvider>
  );
};

// Иконки уведомлений (стеклянные плашки в стиле iOS)
const TOAST_ICONS = {
  success: <Check size={17} strokeWidth={2.8} />,
  info: <Info size={17} strokeWidth={2.8} />,
  warning: <AlertTriangle size={17} strokeWidth={2.5} />,
  error: <X size={17} strokeWidth={3} />,
  loading: <Loader2 size={17} strokeWidth={2.6} className="twb-spin" />,
  close: <X size={11} strokeWidth={3.2} />,
};

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Toaster
            position="top-center"
            theme="dark"
            offset={{ top: 12 }}
            mobileOffset={{ top: 10, left: 12, right: 12 }}
            gap={10}
            visibleToasts={3}
            closeButton
            duration={4200}
            icons={TOAST_ICONS}
            toastOptions={{ closeButtonAriaLabel: "Закрыть уведомление" }}
          />
          <ErrorBoundary>
            <AppShell />
          </ErrorBoundary>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
