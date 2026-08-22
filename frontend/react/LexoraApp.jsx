import { useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  buildDemoEvidence,
  buildProcessedQuery,
  requestApi,
} from "./apiClient.js";

const THEME_KEY = "lexora-theme";

const navItems = [
  ["index.html", "الرئيسية"],
  ["dashboard.html", "لوحة العمل"],
  ["consultation.html", "القضايا والبحث"],
  ["auth.html", "الدخول والصلاحيات"],
];

const cases = [
  {
    id: "LEX-1024",
    title: "نزاع عقد توريد",
    client: "شركة النور",
    lawyer: "محامي 1",
    type: "تجاري",
    priority: "متوسطة",
    status: "نشطة",
    deadline: "24 أغسطس",
    scope: "lawyer",
  },
  {
    id: "LEX-1025",
    title: "استئناف حكم عمالي",
    client: "أحمد سالم",
    lawyer: "محامي 1",
    type: "عمل",
    priority: "عاجلة",
    status: "عاجلة",
    deadline: "25 أغسطس",
    scope: "lawyer",
  },
  {
    id: "LEX-1026",
    title: "قسمة تركة",
    client: "عائلة حسن",
    lawyer: "محامي 2",
    type: "ميراث",
    priority: "عادية",
    status: "معلقة",
    deadline: "28 أغسطس",
    scope: "manager",
  },
  {
    id: "LEX-1027",
    title: "مراجعة اتفاقية شراكة",
    client: "بيتا للاستثمار",
    lawyer: "محامي 3",
    type: "عقود",
    priority: "منخفضة",
    status: "مغلقة",
    deadline: "لا يوجد",
    scope: "manager",
  },
];

function getPage() {
  const path = window.location.pathname.toLowerCase();
  if (path.endsWith("dashboard.html")) return "dashboard";
  if (path.endsWith("consultation.html")) return "consultation";
  if (path.endsWith("auth.html")) return "auth";
  return "home";
}

export function useLexoraTheme() {
  const [theme, setThemeState] = useState(
    () => localStorage.getItem(THEME_KEY) || "light",
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  function toggleTheme() {
    document.documentElement.classList.add("theme-changing");
    setThemeState((current) => (current === "dark" ? "light" : "dark"));
    window.setTimeout(
      () => document.documentElement.classList.remove("theme-changing"),
      520,
    );
  }

  return {
    theme,
    toggleTheme,
    themeLabel: theme === "dark" ? "الوضع الفاتح" : "الوضع الغامق",
  };
}

export function ThemeButton() {
  const { theme, toggleTheme, themeLabel } = useLexoraTheme();

  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label="تبديل الوضع الليلي"
      aria-pressed={theme === "dark"}
      onClick={toggleTheme}
    >
      <span className="theme-toggle-track" aria-hidden="true" />
      <span>{themeLabel}</span>
    </button>
  );
}

function Header({ active = "home" }) {
  return (
    <header className="navbar">
      <a className="brand" href="index.html">
        AI-Lexora
        <small>Legal Intelligence Workspace</small>
      </a>
      <nav>
        {navItems.map(([href, label]) => (
          <a
            className={
              (active === "home" && href === "index.html")
              || href.startsWith(active)
                ? "active"
                : undefined
            }
            href={href}
            key={href}
          >
            {label}
          </a>
        ))}
      </nav>
      <div className="nav-tools">
        <ThemeButton />
        <a className="nav-action" href="dashboard.html">فتح النظام</a>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <p>AI-Lexora - Internal Legal Management & AI Workspace.</p>
      <div>
        <a href="dashboard.html">Dashboard</a>
        <a href="auth.html">Settings</a>
      </div>
    </footer>
  );
}

export function BackendStatusPanel() {
  const [output, setOutput] = useState({ status: "waiting", apiBase: API_BASE });
  const [loading, setLoading] = useState("");

  async function check(path) {
    setLoading(path);
    setOutput({ status: "loading", endpoint: path });

    try {
      setOutput(await requestApi(path));
    } catch (error) {
      setOutput({
        status: "error",
        endpoint: path,
        apiBase: API_BASE,
        message: error.message,
      });
    } finally {
      setLoading("");
    }
  }

  return (
    <section className="api-section">
      <div className="table-header">
        <div>
          <p className="eyebrow">Backend Control</p>
          <h2>اختبر اتصال الواجهة بالباك اند</h2>
          <p>القيمة الافتراضية للـ API هي {API_BASE}.</p>
        </div>
        <div className="quick-actions">
          <button className="ghost-btn" type="button" disabled={loading === "/health"} onClick={() => check("/health")}>
            Health
          </button>
          <button className="primary-btn" type="button" disabled={loading === "/ready"} onClick={() => check("/ready")}>
            Readiness
          </button>
        </div>
      </div>
      <pre className="api-output">{JSON.stringify(output, null, 2)}</pre>
    </section>
  );
}

export function AiAnswerForm({ mode = "ai" }) {
  const [question, setQuestion] = useState("");
  const [output, setOutput] = useState({ status: "waiting" });
  const [loading, setLoading] = useState(false);

  async function submitAnswer(event) {
    event.preventDefault();
    const trimmedQuestion = question.trim();

    if (!trimmedQuestion) {
      setOutput({ status: "error", message: "اكتب السؤال القانوني الاول." });
      return;
    }

    const processedQuery = buildProcessedQuery(trimmedQuestion);

    if (mode === "rag") {
      setOutput({
        status: "needs_backend_pipeline",
        endpoint: "/api/v1/rag/answer",
        message: "مسار RAG الحالي يحتاج embedding حقيقي من M2، والفرنت لا يولده وحده.",
        required_backend_change: "إضافة endpoint يستقبل السؤال الخام ثم يشغل QueryPipeline قبل RAG.",
        payload_preview: { processed_query: processedQuery },
      });
      return;
    }

    const payload = {
      processed_query: processedQuery,
      retrieved_evidence: buildDemoEvidence(processedQuery.query_id),
    };

    setLoading(true);
    setOutput({ status: "sending", endpoint: "/api/v1/ai/answer", payload });

    try {
      const result = await requestApi("/api/v1/ai/answer", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setOutput({
        status: "success",
        answer: result.answer,
        confidence: result.confidence,
        citations: result.citations || [],
        query_id: result.query_id,
      });
    } catch (error) {
      setOutput({
        status: "error",
        endpoint: "/api/v1/ai/answer",
        message: error.message,
        payload,
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="api-section">
      <form onSubmit={submitAnswer}>
        <label>
          {mode === "rag" ? "سؤال البحث" : "السؤال القانوني"}
          <textarea
            name="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="مثال: هل يجوز إنهاء العقد بدون إخطار كتابي؟"
            required
          />
        </label>
        <button className="submit-btn" type="submit" disabled={loading}>
          {mode === "rag" ? "تشغيل البحث بالمصادر" : "توليد إجابة قانونية"}
        </button>
      </form>
      <pre className="api-output">{JSON.stringify(output, null, 2)}</pre>
    </section>
  );
}

function HomePage() {
  return (
    <>
      <Header active="home" />
      <main>
        <section className="hero">
          <div className="hero-content">
            <p className="eyebrow">إدارة مكتب محاماة + ذكاء اصطناعي قانوني</p>
            <h1>واجهة واحدة لإدارة القضايا وتشغيل البحث القانوني بالمصادر.</h1>
            <p className="hero-text">
              AI-Lexora يجمع متابعة القضايا، فحص جاهزية الباك اند، وتجربة إجابات قانونية موثقة من نفس الواجهة.
            </p>
            <div className="hero-actions">
              <a className="primary-btn" href="dashboard.html">لوحة العمل</a>
              <a className="secondary-btn" href="consultation.html">ابدأ بحث قانوني</a>
            </div>
          </div>
          <aside className="hero-panel">
            <h2>الأوامر المتاحة من الباك اند</h2>
            <ul className="check-list">
              <li>فحص FastAPI عبر /health.</li>
              <li>فحص جاهزية الخدمات عبر /ready.</li>
              <li>توليد إجابة قانونية عبر /api/v1/ai/answer.</li>
              <li>البحث الكامل يحتاج embedding من M2 قبل RAG.</li>
            </ul>
          </aside>
        </section>
        <section className="stats">
          <div><strong>42</strong><span>قضية داخل النظام</span></div>
          <div><strong>11</strong><span>موعد مهم هذا الأسبوع</span></div>
          <div><strong>6</strong><span>مستندات تنتظر المراجعة</span></div>
          <div><strong>4</strong><span>Endpoints جاهزة للتجربة</span></div>
        </section>
        <BackendStatusPanel />
      </main>
      <Footer />
    </>
  );
}

function DashboardPage() {
  const [role, setRole] = useState("manager");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");

  const filteredCases = useMemo(() => cases.filter((item) => {
    const matchesQuery = Object.values(item).join(" ").toLowerCase().includes(query.toLowerCase());
    const matchesStatus = status === "all" || item.status === status;
    const matchesRole = role === "manager" || item.scope !== "manager";
    return matchesQuery && matchesStatus && matchesRole;
  }), [query, role, status]);

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <a className="brand light" href="index.html">
          AI-Lexora
          <small>Operations Console</small>
        </a>
        <nav>
          <a className="active" href="dashboard.html">لوحة العمل</a>
          <a href="consultation.html">{role === "manager" ? "كل القضايا" : "قضاياي"}</a>
          <a href="consultation.html">المستندات</a>
          <a href="consultation.html">Legal Research</a>
          <a href="#ai-console">AI Assistant</a>
          <a href="auth.html">الصلاحيات</a>
        </nav>
        <ThemeButton />
        <p className="sidebar-footer">API Base: {API_BASE}</p>
      </aside>

      <main className="dashboard-main">
        <header className="dashboard-topbar">
          <div>
            <p className="eyebrow">Law Firm Operations</p>
            <h1>لوحة تشغيل المكتب القانوني</h1>
          </div>
          <div className="topbar-actions">
            <label className="role-switch">
              الدور
              <select value={role} onChange={(event) => setRole(event.target.value)}>
                <option value="lawyer">Lawyer</option>
                <option value="manager">Manager / Admin</option>
              </select>
            </label>
            <a className="primary-btn" href="consultation.html">إضافة قضية</a>
          </div>
        </header>

        <section className="dashboard-cards">
          <article className="metric-card"><span>{role === "manager" ? "كل القضايا" : "قضاياي"}</span><strong>{role === "manager" ? 42 : 18}</strong><p>قيد المتابعة</p></article>
          <article className="metric-card"><span>نشطة</span><strong>{role === "manager" ? 29 : 12}</strong><p>داخل نطاق عملي</p></article>
          <article className="metric-card"><span>مهام معلقة</span><strong>7</strong><p>مذكرات ومراجعات</p></article>
          <article className="metric-card"><span>مواعيد قادمة</span><strong>4</strong><p>جلسات وتسليمات</p></article>
        </section>

        <section className="workspace-grid">
          <article className="table-section">
            <div className="table-header">
              <div>
                <h2>{role === "manager" ? "كل قضايا المكتب" : "قضاياي الحالية"}</h2>
                <p>بحث وفلترة حسب الحالة، العميل، المحامي، أو رقم القضية.</p>
              </div>
              <div className="table-tools">
                <input value={query} onChange={(event) => setQuery(event.target.value)} type="search" placeholder="ابحث برقم القضية أو العميل" />
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="all">كل الحالات</option>
                  <option value="نشطة">نشطة</option>
                  <option value="معلقة">معلقة</option>
                  <option value="عاجلة">عاجلة</option>
                  <option value="مغلقة">مغلقة</option>
                </select>
              </div>
            </div>
            <div className="responsive-table">
              <table>
                <thead>
                  <tr>
                    <th>Case ID</th>
                    <th>القضية</th>
                    <th>العميل</th>
                    <th>المحامي</th>
                    <th>النوع</th>
                    <th>الأولوية</th>
                    <th>الحالة</th>
                    <th>الموعد القادم</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCases.map((item) => (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td>{item.title}</td>
                      <td>{item.client}</td>
                      <td>{item.lawyer}</td>
                      <td>{item.type}</td>
                      <td>{item.priority}</td>
                      <td><span className="badge active-case">{item.status}</span></td>
                      <td>{item.deadline}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <aside className="side-stack">
            <BackendStatusPanel />
            <section className="panel-card">
              <h2>مواعيد مهمة</h2>
              <div className="timeline-item"><strong>24</strong><span>تسليم مذكرة دفاع في LEX-1024</span></div>
              <div className="timeline-item"><strong>25</strong><span>جلسة استئناف عمالي في LEX-1025</span></div>
              <div className="timeline-item"><strong>28</strong><span>مراجعة مستندات ميراث في LEX-1026</span></div>
            </section>
          </aside>
        </section>

        <section id="ai-console">
          <AiAnswerForm />
        </section>
      </main>
    </div>
  );
}

function ConsultationPage() {
  return (
    <>
      <Header active="consultation" />
      <main>
        <section className="page-title">
          <p className="eyebrow">Case Management</p>
          <h1>إنشاء قضية وربطها بالمستندات والبحث القانوني.</h1>
          <p>القضايا والمستندات هنا واجهة Frontend جاهزة للربط عند إضافة endpoints مخصصة.</p>
        </section>
        <section className="form-layout">
          <form className="consultation-form">
            <h2>بيانات القضية</h2>
            <div className="form-grid">
              <label>Case ID<input type="text" placeholder="LEX-1028" required /></label>
              <label>عنوان القضية<input type="text" placeholder="دعوى مطالبة مالية" required /></label>
              <label>العميل<input type="text" placeholder="اسم العميل أو الشركة" required /></label>
              <label>المحامي المسؤول<select><option>محامي 1</option><option>محامي 2</option></select></label>
              <label>نوع القضية<select><option>تجاري</option><option>عقود</option><option>عمل</option></select></label>
              <label>الموعد القادم<input type="date" /></label>
            </div>
            <label>ملاحظات القضية<textarea placeholder="ملخص الوقائع والمخاطر..." required /></label>
            <button className="submit-btn" type="button">حفظ ملف القضية محليا</button>
          </form>
          <aside className="info-panel">
            <h2>أوامر مرتبطة بالقضية</h2>
            <div className="timeline-item"><strong>1</strong><span>إنشاء أو تحديث ملف القضية.</span></div>
            <div className="timeline-item"><strong>2</strong><span>رفع مستند يحتاج upload endpoint لاحق.</span></div>
            <div className="timeline-item"><strong>3</strong><span>تجربة المساعد أو البحث بالمصادر.</span></div>
          </aside>
        </section>
        <section className="form-layout">
          <AiAnswerForm />
          <AiAnswerForm mode="rag" />
        </section>
      </main>
      <Footer />
    </>
  );
}

function AuthPage() {
  const [tab, setTab] = useState("login");

  return (
    <>
      <Header active="auth" />
      <main>
        <section className="auth-layout">
          <div className="auth-copy">
            <p className="eyebrow">Access Control</p>
            <h1>دخول داخلي للمحامين والمديرين مع فصل واضح للصلاحيات.</h1>
            <p>الباك الحالي لا يحتوي authentication endpoints، لذلك النموذج Frontend-only.</p>
            <div className="permissions">
              <h2>الأدوار</h2>
              <div><strong>Lawyer</strong><span>قضاياه، مستنداته، مهامه، والبحث القانوني.</span></div>
              <div><strong>Manager / Admin</strong><span>كل القضايا، الفريق، العملاء، التقارير، والصلاحيات.</span></div>
            </div>
          </div>
          <section className="auth-card">
            <div className="tabs">
              {["login", "register", "forgot"].map((item) => (
                <button className={tab === item ? "active" : undefined} type="button" key={item} onClick={() => setTab(item)}>
                  {item === "login" ? "دخول" : item === "register" ? "إضافة موظف" : "استعادة كلمة السر"}
                </button>
              ))}
            </div>
            <form className="auth-form active">
              <h2>{tab === "login" ? "تسجيل الدخول" : tab === "register" ? "إضافة مستخدم داخلي" : "استعادة كلمة المرور"}</h2>
              {tab === "register" && <label>الاسم الكامل<input type="text" required /></label>}
              <label>البريد الإلكتروني<input type="email" placeholder="lawyer@ai-lexora.local" required /></label>
              {tab !== "forgot" && <label>كلمة المرور<input type="password" required /></label>}
              {tab !== "forgot" && <label>الدور<select><option>Lawyer</option><option>Manager / Admin</option></select></label>}
              <button className="submit-btn" type="button">تنفيذ تجريبي</button>
            </form>
          </section>
        </section>
        <BackendStatusPanel />
      </main>
      <Footer />
    </>
  );
}

export default function LexoraApp() {
  const page = getPage();

  if (page === "dashboard") return <DashboardPage />;
  if (page === "consultation") return <ConsultationPage />;
  if (page === "auth") return <AuthPage />;
  return <HomePage />;
}
