import { demoCases, demoLawyers } from "./frontend/demoData.js";

const API_BASE = window.AI_LEXORA_API_BASE || "http://localhost:8000";
let documentParserPromise;

function loadDocumentParser() {
  documentParserPromise ||= import("./frontend/utils/documentParser.js");
  return documentParserPromise;
}

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
  let payload = {};

  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { detail: "استجاب الخادم بتنسيق غير صالح." };
  }

  if (!response.ok) {
    const message = payload.error?.message || payload.detail || `Request failed with status ${response.status}`;
    throw new Error(Array.isArray(message) ? message.map((item) => item.msg).join("، ") : message);
  }

  return payload;
}

function renderJson(target, payload) {
  if (!target) return;
  target.textContent = JSON.stringify(payload, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#039;",
  }[char]));
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


document.querySelectorAll("form:not([data-file-search-form])").forEach((form) => {
  form.addEventListener("invalid", (event) => {
    form.classList.add("was-validated");
    event.target.setAttribute("aria-invalid", "true");
  }, true);
  form.querySelectorAll("input, select, textarea").forEach((control) => {
    control.addEventListener("input", () => control.setAttribute("aria-invalid", control.validity.valid ? "false" : "true"));
    control.addEventListener("change", () => control.setAttribute("aria-invalid", control.validity.valid ? "false" : "true"));
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    form.classList.add("was-validated");
    form.querySelectorAll("input, select, textarea").forEach((control) => {
      control.setAttribute("aria-invalid", control.validity.valid ? "false" : "true");
    });
    if (form.checkValidity()) {
      const message = form.dataset.success || "تم تنفيذ العملية بنجاح.";
      showToast(message, "success");
      form.reset();
      form.classList.remove("was-validated");
      form.querySelectorAll("input, select, textarea").forEach((control) => control.setAttribute("aria-invalid", "false"));
    }
  });
});

const searchInput = document.querySelector("[data-search]");
const filterSelect = document.querySelector("[data-filter]");
const tableBody = document.querySelector("[data-cases-table]");
const emptyState = document.querySelector("[data-empty]");
const roleSwitch = document.querySelector("[data-role-switch]");
const modal = document.querySelector("[data-modal]");
const modalTitle = modal?.querySelector("[data-modal-title]");
const modalContext = modal?.querySelector("[data-modal-context]");
const modalSave = modal?.querySelector("[data-save-modal]");
const modalSecondary = modal?.querySelector("[data-modal-secondary]");
const modalFields = {
  id: modal?.querySelector("[data-modal-case-id]"),
  title: modal?.querySelector("[data-modal-case-title]"),
  client: modal?.querySelector("[data-modal-case-client]"),
  lawyer: modal?.querySelector("[data-modal-case-lawyer]"),
  status: modal?.querySelector("[data-modal-case-status]"),
};
const dashboardCases = [...demoCases];
let modalMode = "create";
let modalCaseId = "";
let lastModalTrigger = null;

function statusClass(status) {
  return {
    نشطة: "active-case",
    عاجلة: "urgent",
    معلقة: "review",
    مغلقة: "closed",
  }[status] || "review";
}

function renderCaseRows() {
  if (!tableBody) return;

  tableBody.innerHTML = dashboardCases.map((item) => `
    <tr data-row-case-id="${escapeHtml(item.id)}" data-status="${escapeHtml(item.status)}" data-scope="${item.lawyer === "محامي 1" ? "lawyer" : "manager"}">
      <td>${escapeHtml(item.id)}</td>
      <td>${escapeHtml(item.title)}</td>
      <td>${escapeHtml(item.client)}</td>
      <td>${escapeHtml(item.lawyer)}</td>
      <td>${escapeHtml(item.category || "غير محدد")}</td>
      <td>${escapeHtml(item.priority || "عادية")}</td>
      <td><span class="badge ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
      <td>${escapeHtml(item.deadline || "لا يوجد")}</td>
      <td class="actions">
        <button type="button" data-case-action="view" data-case-id="${escapeHtml(item.id)}">عرض</button>
        <button type="button" data-case-action="edit" data-case-id="${escapeHtml(item.id)}">تعديل</button>
        <button type="button" data-case-action="assign" data-case-id="${escapeHtml(item.id)}">تعيين</button>
      </td>
    </tr>
  `).join("");

  tableBody.querySelectorAll("[data-case-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = dashboardCases.find((candidate) => candidate.id === button.dataset.caseId);
      if (!item) return;
      openCaseModal(button.dataset.caseAction, item, button);
    });
  });
}

function setModalFieldValues(item = {}) {
  Object.entries(modalFields).forEach(([field, input]) => {
    if (input) input.value = item[field] || "";
  });
}

function setModalMode(mode, item = null, trigger = null) {
  modalMode = mode;
  modalCaseId = item?.id || "";
  lastModalTrigger = trigger;
  setModalFieldValues(item || {});

  const isView = mode === "view";
  const isAssign = mode === "assign";
  const labels = {
    create: "إضافة قضية تجريبية",
    view: "عرض بيانات القضية",
    edit: "تعديل قضية تجريبية",
    assign: "تعيين محامٍ تجريبي",
  };
  const contexts = {
    create: "هذه البيانات تجريبية وتظهر في الجدول الحالي فقط.",
    view: "عرض محلي فقط. لا توجد عملية Backend لتفاصيل القضية حاليًا.",
    edit: "التعديل محلي ويستمر أثناء فتح الصفحة فقط.",
    assign: "التعيين محلي فقط. لن يتم تحديث نظام الصلاحيات حاليًا.",
  };

  if (modalTitle) modalTitle.textContent = labels[mode];
  if (modalContext) modalContext.textContent = contexts[mode];
  if (modalSave) {
    modalSave.hidden = isView;
    modalSave.textContent = mode === "assign" ? "حفظ التعيين محليًا" : mode === "create" ? "إضافة للعرض التجريبي" : "حفظ التعديل المحلي";
  }
  if (modalSecondary) {
    modalSecondary.toggleAttribute("hidden", !isView);
    modalSecondary.textContent = "إغلاق القضية (Demo)";
  }
  Object.entries(modalFields).forEach(([field, input]) => {
    if (!input) return;
    input.disabled = isView || (isAssign && !["lawyer"].includes(field));
  });
  if (modal) {
    modal.hidden = false;
    window.setTimeout(() => (isView ? modalFields.title : modalFields.id)?.focus(), 0);
  }
}

function openCaseModal(mode, item = null, trigger = null) {
  setModalMode(mode, item, trigger);
}

function closeCaseModal() {
  if (!modal) return;
  modal.hidden = true;
  lastModalTrigger?.focus();
  lastModalTrigger = null;
}

function saveCaseModal() {
  const values = Object.fromEntries(
    Object.entries(modalFields).map(([field, input]) => [field, input?.value.trim() || ""]),
  );

  if (modalMode === "create") {
    if (!values.id || !values.title || !values.client) {
      showToast("أكمل رقم القضية والعنوان والعميل قبل الإضافة.", "error");
      return;
    }
    if (dashboardCases.some((item) => item.id === values.id)) {
      showToast("رقم القضية مستخدم بالفعل في البيانات التجريبية.", "error");
      return;
    }
    dashboardCases.push({
      ...values,
      category: "غير محدد",
      priority: "عادية",
      deadline: "لا يوجد",
    });
    renderCaseRows();
    applyTableFilters();
    closeCaseModal();
    showToast("تمت إضافة القضية للعرض التجريبي فقط.", "info");
    return;
  }

  const item = dashboardCases.find((candidate) => candidate.id === modalCaseId);
  if (!item) return;
  Object.assign(item, values);
  renderCaseRows();
  applyTableFilters();
  closeCaseModal();
  showToast(modalMode === "assign" ? "تم تحديث المحامي في العرض التجريبي فقط." : "تم تحديث القضية في العرض التجريبي فقط.", "info");
}

renderCaseRows();

document.querySelector("[data-open-modal]")?.addEventListener("click", (event) => {
  openCaseModal("create", null, event.currentTarget);
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
  button.addEventListener("click", closeCaseModal);
});

modalSave?.addEventListener("click", saveCaseModal);
modalSecondary?.addEventListener("click", () => {
  const item = dashboardCases.find((candidate) => candidate.id === modalCaseId);
  if (!item) return;
  item.status = "مغلقة";
  renderCaseRows();
  applyTableFilters();
  closeCaseModal();
  showToast("تم إغلاق القضية في العرض التجريبي فقط.", "info");
});

modal?.addEventListener("click", (event) => {
  if (event.target === modal) closeCaseModal();
});

modal?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeCaseModal();

  if (event.key !== "Tab") return;
  const focusable = Array.from(
    modal.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])"),
  );
  if (!focusable.length) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});

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

function formatAttachmentSize(size) {
  if (!size) return "0 KB";
  if (size < 1024 * 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

document.querySelectorAll("[data-file-search-form]").forEach((form) => {
  const fileInput = form.querySelector("[data-search-files]");
  const clearButton = form.querySelector("[data-clear-search-files]");
  const fileList = form.querySelector("[data-search-file-list]");
  const output = form.parentElement?.querySelector("[data-file-search-output]");
  const submitButton = form.querySelector("button[type=submit]");
  let selectedFiles = [];
  let searchLoading = false;

  function renderSearchFiles() {
    if (!fileList) return;
    fileList.innerHTML = "";

    selectedFiles.forEach((item, fileIndex) => {
      const chip = document.createElement("span");
      chip.className = "attachment-chip";

      const text = document.createElement("span");
      text.textContent = `${item.file.name} (${item.extension || "غير معروف"})`;

      const meta = document.createElement("small");
      meta.textContent = item.status === "error"
        ? item.error
        : `${item.status === "ready" ? "تمت القراءة" : "قيد القراءة"} - ${formatAttachmentSize(item.file.size)}`;
      text.appendChild(meta);

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.setAttribute("aria-label", `حذف ${item.file.name}`);
      removeButton.addEventListener("click", () => {
        selectedFiles.splice(fileIndex, 1);
        renderSearchFiles();
        if (activeSearchTerm) renderCurrentSearch();
      });

      chip.append(text, removeButton);
      fileList.appendChild(chip);
    });
  }

  function highlightText(text, term) {
    const escapedText = escapeHtml(text);
    if (!term) return escapedText;

    const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

    return escapedText.replace(
      new RegExp(escapedTerm, "gi"),
      (match) => `<mark class="search-highlight">${escapeHtml(match)}</mark>`
    );
  }

  function readFileAsText(file) {
    return new Promise((resolve) => {
      const reader = new FileReader();

      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => resolve("");
      reader.readAsText(file);
    });
  }

  function findFileSearchResults(term) {
    const normalizedTerm = term.toLocaleLowerCase();
    const results = [];

    for (const item of selectedFiles) {
      if (item.status !== "ready" || !item.parsed?.text) continue;

      const content = item.parsed.text;
      const matches = content.match(
        new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"),
      ) || [];

      if (matches.length) {
        results.push({
          fileName: item.file.name,
          fileType: item.parsed.extension.toUpperCase(),
          content,
          matchCount: matches.length,
          pages: item.parsed.pages.filter((page) =>
            page.text.toLocaleLowerCase().includes(normalizedTerm),
          ),
        });
      }
    }

    return results;
  }

  function renderFileSearchResults(results, term) {
    if (!output) return;
    output.dataset.state = results.length ? "success" : "waiting";

    if (!selectedFiles.length) {
      output.innerHTML = `
        <h3>ارفع ملف أولا</h3>
        <p>اختار ملف أو أكثر قبل البحث.</p>
      `;
      return;
    }

    if (!results.length) {
      output.innerHTML = `
        <h3>لا توجد نتيجة مطابقة</h3>
        <p>جرب كلمة مختلفة أو تحقق من حالة قراءة الملفات.</p>
      `;
      return;
    }

    output.innerHTML = results.map((result) => `
      <article class="file-result-card">
        <strong>${escapeHtml(result.fileName)} <small>${escapeHtml(result.fileType)}</small></strong>
        <span>عدد التطابقات: ${result.matchCount}</span>
        <p>${highlightText(result.content, term)}</p>
        ${result.pages.length ? `<span>الصفحات المطابقة: ${result.pages.map((page) => page.page).join(", ")}</span>` : ""}
      </article>
    `).join("");
  }

  let activeSearchTerm = "";

  function renderCurrentSearch() {
    if (!activeSearchTerm) return;
    renderFileSearchResults(findFileSearchResults(activeSearchTerm), activeSearchTerm);
  }

  fileInput?.addEventListener("change", async (event) => {
    const incomingFiles = Array.from(event.target.files || []);
    const knownKeys = new Set(selectedFiles.map(({ file }) => `${file.name}_${file.size}_${file.lastModified}`));
    const newItems = incomingFiles.filter((file) => !knownKeys.has(`${file.name}_${file.size}_${file.lastModified}`));
    let parser;

    try {
      parser = await loadDocumentParser();
    } catch {
      showToast("تعذر تحميل قارئ الملفات. استخدم TXT أو MD أو CSV أو JSON مؤقتا.", "error");
      return;
    }

    const validatedItems = newItems.map((file) => {
      try {
        return { file, extension: parser.validateDocumentFile(file), status: "reading" };
      } catch (error) {
        showToast(error.message, "error");
        return { file, status: "error", error: error.message };
      }
    });
    selectedFiles = [...selectedFiles, ...validatedItems];
    renderSearchFiles();
    event.target.value = "";

    validatedItems.filter((item) => item.status === "reading").forEach(async (item) => {
      try {
        item.parsed = await parser.parseDocumentFile(item.file);
        item.status = "ready";
      } catch (error) {
        item.status = "error";
        item.error = error.message;
        showToast(`${item.file.name}: ${error.message}`, "error");
      }
      renderSearchFiles();
      if (activeSearchTerm) renderCurrentSearch();
    });
  });

  clearButton?.addEventListener("click", () => {
    selectedFiles = [];
    activeSearchTerm = "";
    renderSearchFiles();
    if (output) {
      output.dataset.state = "waiting";
      output.innerHTML = `
        <h3>ارفع ملف وابدأ البحث</h3>
        <p>يدعم البحث داخل TXT وMD وCSV وJSON وPDF وDOCX. ملفات DOC القديمة غير قابلة للقراءة الموثوقة داخل المتصفح.</p>
      `;
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (searchLoading) return;
    const term = new FormData(form).get("searchTerm")?.toString().trim();

    if (!term) {
      showToast("اكتب كلمة البحث الأول.", "error");
      return;
    }

    if (selectedFiles.some((item) => item.status === "reading")) {
      showToast("انتظر حتى تكتمل قراءة الملفات.", "error");
      return;
    }

    if (selectedFiles.every((item) => item.status !== "ready")) {
      showToast("لا يوجد ملف صالح للبحث.", "error");
      return;
    }

    searchLoading = true;
    activeSearchTerm = term;
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "جاري البحث...";
    }
    if (output) {
      output.dataset.state = "searching";
      output.innerHTML = "<h3>جاري البحث...</h3><p>يتم فحص المستندات المحددة الآن.</p>";
    }

    try {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
      const results = findFileSearchResults(term);
      renderFileSearchResults(results, term);
      showToast(results.length ? "تم العثور على نتائج داخل الملفات." : "لا توجد نتيجة مطابقة.", results.length ? "success" : "error");
    } catch {
      if (output) {
        output.dataset.state = "error";
        output.innerHTML = "<h3>تعذر تنفيذ البحث</h3><p>حدث خطأ أثناء فحص الملفات. حاول مرة أخرى.</p><button class=\"ghost-btn\" type=\"button\" data-search-retry>إعادة المحاولة</button>";
        output.querySelector("[data-search-retry]")?.addEventListener("click", () => form.requestSubmit());
      }
      showToast("تعذر تنفيذ البحث. حاول مرة أخرى.", "error");
    } finally {
      searchLoading = false;
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "بحث داخل الملفات";
      }
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
