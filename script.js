const API_BASE = window.AI_LEXORA_API_BASE || "http://localhost:8000";

const toast = document.querySelector("[data-toast]");
const themeToggles = document.querySelectorAll("[data-theme-toggle]");

function showToast(message, type = "info") {
  if (!toast) return;
  toast.textContent = message;
  toast.dataset.type = type;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("lexora-theme", theme);
  themeToggles.forEach((toggle) => {
    const label = toggle.querySelector("[data-theme-label]");
    if (label) label.textContent = theme === "dark" ? "الوضع الفاتح" : "الوضع الغامق";
    toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  });
}

setTheme(localStorage.getItem("lexora-theme") || "light");

themeToggles.forEach((toggle) => {
  toggle.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.classList.add("theme-changing");
    setTheme(next);
    window.setTimeout(() => document.documentElement.classList.remove("theme-changing"), 520);
    showToast(next === "dark" ? "تم تفعيل الوضع الغامق." : "تم تفعيل الوضع الفاتح.");
  });
});

async function requestApi(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};

  if (!response.ok) {
    const message = payload.detail || `Request failed with status ${response.status}`;
    throw new Error(Array.isArray(message) ? message.map((item) => item.msg).join("، ") : message);
  }

  return payload;
}

function renderJson(target, payload) {
  if (!target) return;
  target.textContent = JSON.stringify(payload, null, 2);
}

function renderApiResult(target, endpoint, result) {
  renderJson(target, {
    status: "success",
    endpoint,
    answer: result.answer,
    confidence: result.confidence,
    citations: result.citations || [],
    query_id: result.query_id,
  });
}

function renderRagCompatibilityNotice(target, payload) {
  renderJson(target, {
    status: "needs_backend_pipeline",
    endpoint: "/api/v1/rag/answer",
    message: "مسار RAG الحالي في الباك يحتاج processed_query يحتوي embedding حقيقي من M2، والفرنت لا يستطيع توليده وحده.",
    required_backend_change: "إضافة endpoint يستقبل السؤال الخام ثم يشغل QueryPipeline قبل /api/v1/rag/answer.",
    current_payload_preview: payload,
  });
}

function setStatusCard(target, state, label, detail) {
  if (!target) return;
  target.dataset.state = state;
  target.querySelector("[data-status-label]").textContent = label;
  target.querySelector("[data-status-detail]").textContent = detail;
}

document.querySelectorAll("[data-check-health]").forEach((button) => {
  button.addEventListener("click", async () => {
    const output = document.querySelector(button.dataset.output || "[data-api-output]");
    const card = document.querySelector("[data-health-card]");
    button.disabled = true;
    setStatusCard(card, "loading", "جاري الفحص", "بنراجع هل FastAPI شغال.");

    try {
      const payload = await requestApi("/health");
      renderJson(output, payload);
      setStatusCard(card, "ready", "متصل", "خدمة FastAPI تعمل بشكل طبيعي.");
      showToast("FastAPI متصل.", "success");
    } catch (error) {
      setStatusCard(card, "error", "غير متصل", error.message);
      renderJson(output, { error: error.message, apiBase: API_BASE });
      showToast("تعذر الاتصال بالباك اند.", "error");
    } finally {
      button.disabled = false;
    }
  });
});

document.querySelectorAll("[data-check-ready]").forEach((button) => {
  button.addEventListener("click", async () => {
    const output = document.querySelector(button.dataset.output || "[data-api-output]");
    const card = document.querySelector("[data-ready-card]");
    button.disabled = true;
    setStatusCard(card, "loading", "جاري الفحص", "بنراجع خدمات الذكاء الاصطناعي والفهرسة.");

    try {
      const payload = await requestApi("/ready");
      renderJson(output, payload);
      const ready = payload.status === "ready";
      setStatusCard(
        card,
        ready ? "ready" : "error",
        ready ? "جاهز" : "غير جاهز",
        payload.detail || "كل مكونات الذكاء الاصطناعي جاهزة."
      );
      showToast(ready ? "النظام جاهز." : "النظام يحتاج تشغيل مكونات.", ready ? "success" : "error");
    } catch (error) {
      setStatusCard(card, "error", "غير جاهز", error.message);
      renderJson(output, { error: error.message, apiBase: API_BASE });
      showToast("فحص الجاهزية فشل.", "error");
    } finally {
      button.disabled = false;
    }
  });
});

function buildProcessedQuery(text, language = "ar") {
  return {
    query_id: `q_front_${Date.now()}`,
    text_original: text,
    normalized_text: text.trim(),
    language,
    embedding: [],
    sparse_embedding: null,
    filters: {
      document_type: null,
      jurisdiction: "Egypt",
      language: null,
      extra_filters: {},
    },
    query_variants: [text.trim()],
    identifiers: {
      article_numbers: [],
      case_numbers: [],
      dates: [],
      monetary_values: [],
      party_names: [],
    },
  };
}

function buildDemoEvidence(queryId) {
  return {
    query_id: queryId,
    retrieved_evidence: [
      {
        document_id: "demo_contract_001",
        chunk_id: "chunk_12",
        text: "لا يجوز إنهاء العقد إلا بعد إخطار كتابي سابق ومنح الطرف الآخر مهلة مناسبة للمعالجة.",
        page: 4,
        section: "شرط الإنهاء",
        language: "ar",
        score: 0.92,
      },
      {
        document_id: "demo_labor_002",
        chunk_id: "chunk_07",
        text: "يجب أن تكون الجزاءات والتزامات الإخطار مرتبطة بنصوص العقد والقانون المنظم للعلاقة.",
        page: 9,
        section: "الالتزامات",
        language: "ar",
        score: 0.81,
      },
    ],
  };
}

document.querySelectorAll("[data-ai-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const output = document.querySelector(form.dataset.output || "[data-api-output]");
    const button = form.querySelector("button[type='submit']");
    const question = new FormData(form).get("question")?.toString().trim();

    if (!question) {
      showToast("اكتب السؤال القانوني الأول.", "error");
      return;
    }

    const processedQuery = buildProcessedQuery(question);
    const payload = {
      processed_query: processedQuery,
      retrieved_evidence: buildDemoEvidence(processedQuery.query_id),
    };

    button.disabled = true;
    renderJson(output, { status: "sending", endpoint: "/api/v1/ai/answer", payload });

    try {
      const result = await requestApi("/api/v1/ai/answer", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      renderApiResult(output, "/api/v1/ai/answer", result);
      showToast("تم توليد إجابة قانونية بالمصادر.", "success");
    } catch (error) {
      renderJson(output, { error: error.message, endpoint: "/api/v1/ai/answer", payload });
      showToast("تعذر توليد الإجابة. تأكد من خدمة الذكاء الاصطناعي.", "error");
    } finally {
      button.disabled = false;
    }
  });
});

document.querySelectorAll("[data-rag-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const output = document.querySelector(form.dataset.output || "[data-api-output]");
    const button = form.querySelector("button[type='submit']");
    const question = new FormData(form).get("question")?.toString().trim();

    if (!question) {
      showToast("اكتب سؤال البحث القانوني الأول.", "error");
      return;
    }

    const payload = { processed_query: buildProcessedQuery(question) };
    if (!payload.processed_query.embedding.length) {
      renderRagCompatibilityNotice(output, payload);
      showToast("البحث الكامل يحتاج embedding من الباك قبل استدعاء RAG.", "error");
      return;
    }

    button.disabled = true;
    renderJson(output, { status: "sending", endpoint: "/api/v1/rag/answer", payload });

    try {
      const result = await requestApi("/api/v1/rag/answer", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      renderJson(output, result);
      showToast("تم تنفيذ البحث بالمصادر.", "success");
    } catch (error) {
      renderJson(output, {
        error: error.message,
        note: "هذا المسار يحتاج بيانات بحث مفهرسة وقاعدة مصادر جاهزة.",
        endpoint: "/api/v1/rag/answer",
        payload,
      });
      showToast("البحث بالمصادر يحتاج تجهيز الفهرسة وقاعدة المصادر.", "error");
    } finally {
      button.disabled = false;
    }
  });
});

document.querySelectorAll("form:not([data-ai-form]):not([data-rag-form])").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    form.classList.add("was-validated");
    if (form.checkValidity()) {
      const message = form.dataset.success || "تم تنفيذ العملية بنجاح.";
      showToast(message, "success");
      form.reset();
      form.classList.remove("was-validated");
    }
  });
});

const modal = document.querySelector("[data-modal]");

document.querySelectorAll("[data-open-modal]").forEach((button) => {
  button.addEventListener("click", () => {
    if (modal) modal.hidden = false;
  });
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
  button.addEventListener("click", () => {
    if (modal) modal.hidden = true;
  });
});

document.querySelectorAll("[data-save-modal]").forEach((button) => {
  button.addEventListener("click", () => {
    if (modal) modal.hidden = true;
    showToast("تم حفظ بيانات القضية محليا.", "success");
  });
});

const searchInput = document.querySelector("[data-search]");
const filterSelect = document.querySelector("[data-filter]");
const tableBody = document.querySelector("[data-cases-table]");
const emptyState = document.querySelector("[data-empty]");
const roleSwitch = document.querySelector("[data-role-switch]");

function getSelectedRole() {
  return roleSwitch?.value || "lawyer";
}

function applyTableFilters() {
  if (!tableBody) return;
  const query = (searchInput?.value || "").trim().toLowerCase();
  const status = filterSelect?.value || "all";
  const role = getSelectedRole();
  let visibleRows = 0;

  tableBody.querySelectorAll("tr").forEach((row) => {
    const matchesSearch = row.textContent.toLowerCase().includes(query);
    const matchesStatus = status === "all" || row.dataset.status === status;
    const matchesRole = role === "manager" || row.dataset.scope !== "manager";
    const shouldShow = matchesSearch && matchesStatus && matchesRole;
    row.hidden = !shouldShow;
    if (shouldShow) visibleRows += 1;
  });

  if (emptyState) emptyState.hidden = visibleRows !== 0;
}

function applyRoleView() {
  const role = getSelectedRole();

  document.querySelectorAll("[data-role-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.rolePanel !== role;
  });

  document.querySelectorAll("[data-nav-lawyer]").forEach((item) => {
    item.hidden = role !== "lawyer";
  });

  document.querySelectorAll("[data-nav-manager], [data-manager-only]").forEach((item) => {
    item.hidden = role !== "manager";
  });

  document.querySelectorAll("[data-title-lawyer]").forEach((item) => {
    item.hidden = role !== "lawyer";
  });

  document.querySelectorAll("[data-title-manager]").forEach((item) => {
    item.hidden = role !== "manager";
  });

  applyTableFilters();
}

searchInput?.addEventListener("input", applyTableFilters);
filterSelect?.addEventListener("change", applyTableFilters);
roleSwitch?.addEventListener("change", applyRoleView);

document.querySelector("[data-sort]")?.addEventListener("click", () => {
  if (!tableBody) return;
  Array.from(tableBody.querySelectorAll("tr"))
    .sort((a, b) => a.children[2].textContent.localeCompare(b.children[2].textContent, "ar"))
    .forEach((row) => tableBody.appendChild(row));
  applyTableFilters();
  showToast("تم ترتيب الجدول حسب اسم العميل.", "success");
});

document.querySelectorAll("[data-auth-tab]").forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.authTab;
    document.querySelectorAll("[data-auth-tab]").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll("[data-auth-panel]").forEach((panel) => panel.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`[data-auth-panel="${target}"]`)?.classList.add("active");
  });
});

document.querySelectorAll("[data-show-toast]").forEach((button) => {
  button.addEventListener("click", () => {
    showToast(button.dataset.showToast || "تم تنفيذ الأمر.", button.dataset.toastType || "info");
  });
});

document.querySelectorAll("[data-copy-endpoint]").forEach((button) => {
  button.addEventListener("click", async () => {
    const endpoint = button.dataset.copyEndpoint;
    try {
      await navigator.clipboard.writeText(`${API_BASE}${endpoint}`);
      showToast("تم نسخ رابط الـ endpoint.", "success");
    } catch {
      showToast(`${API_BASE}${endpoint}`);
    }
  });
});

const animatedElements = document.querySelectorAll(
  ".hero, .page-title, .stats > *, .service-card, .metric-card, .table-section, .api-section, .panel-card, .document-card, .consultation-form, .info-panel, .auth-copy, .auth-card, .permissions, .endpoint-card, .requirements-band"
);

animatedElements.forEach((element, index) => {
  element.dataset.animate = element.dataset.animate || "fade-up";
  element.style.setProperty("--delay", `${Math.min(index % 8, 7) * 55}ms`);
});

if ("IntersectionObserver" in window) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      });
    },
    {
      threshold: 0.14,
      rootMargin: "0px 0px -48px 0px",
    }
  );

  animatedElements.forEach((element) => revealObserver.observe(element));
} else {
  animatedElements.forEach((element) => element.classList.add("is-visible"));
}

applyRoleView();
