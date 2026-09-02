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
  const payload = text ? JSON.parse(text) : {};

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
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#039;",
  }[char]));
}

function renderAgentResult(target, payload) {
  if (!target) return;

  const state = payload.status === "error" ? "error" : "success";
  target.dataset.state = state;

  const meta = [];
  if (payload.endpoint) meta.push(payload.endpoint);
  if (payload.attachments?.length) meta.push(`${payload.attachments.length} مرفقات`);
  if (payload.confidence !== undefined) meta.push(`ثقة ${Math.round(payload.confidence * 100)}%`);

  target.innerHTML = `
    <h3>${escapeHtml(payload.title || "نتيجة المساعد")}</h3>
    <p>${escapeHtml(payload.answer || payload.message || "تم تجهيز السؤال للربط مع خدمة الذكاء الاصطناعي.")}</p>
    ${meta.length ? `<div class="agent-meta">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
  `;
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


document
  .querySelectorAll("[data-ai-form], [data-rag-form]")
  .forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();

      showToast(
        "هذه الواجهة القديمة غير مفعلة. استخدم واجهة المساعد القانوني المتصلة بالنظام.",
        "error"
      );
    });
  });


document.querySelectorAll("form:not([data-ai-form]):not([data-rag-form]):not([data-file-search-form]):not([data-agent-form])").forEach((form) => {
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

function formatAttachmentSize(size) {
  if (!size) return "0 KB";
  if (size < 1024 * 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

document.querySelectorAll("[data-agent-form]").forEach((form) => {
  const attachmentToggle = form.querySelector("[data-attachment-toggle]");
  const attachmentMenu = form.querySelector("[data-attachment-menu]");
  const fileInput = form.querySelector("[data-file-input]");
  const imageInput = form.querySelector("[data-image-input]");
  const cameraInput = form.querySelector("[data-camera-input]");
  const filePicker = form.querySelector("[data-pick-files]");
  const cameraPicker = form.querySelector("[data-pick-camera]");
  const imagePicker = form.querySelector("[data-pick-image]");
  const attachmentList = form.querySelector("[data-attachment-list]");
  const output = form.parentElement?.querySelector("[data-agent-output]");
  const attachments = [];

  function closeAttachmentMenu() {
    if (!attachmentMenu || !attachmentToggle) return;
    attachmentMenu.hidden = true;
    attachmentToggle.setAttribute("aria-expanded", "false");
  }

  function renderAttachments() {
    if (!attachmentList) return;
    attachmentList.innerHTML = "";

    attachments.forEach((attachment) => {
      const chip = document.createElement("span");
      chip.className = "attachment-chip";

      const text = document.createElement("span");
      text.textContent = attachment.name;

      const meta = document.createElement("small");
      meta.textContent = `${attachment.source === "camera" ? "كاميرا" : attachment.source === "image" ? "صورة" : "ملف"} - ${attachment.sizeLabel}`;
      text.appendChild(meta);

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.textContent = "x";
      removeButton.setAttribute("aria-label", `حذف ${attachment.name}`);
      removeButton.addEventListener("click", () => {
        const index = attachments.findIndex((item) => item.id === attachment.id);
        if (index >= 0) attachments.splice(index, 1);
        renderAttachments();
      });

      chip.append(text, removeButton);
      attachmentList.appendChild(chip);
    });
  }

  function addAttachments(fileList, source) {
    Array.from(fileList || []).forEach((file) => {
      const attachment = {
        id: `${source}_${file.name}_${file.lastModified}_${file.size}`,
        name: file.name || "camera-image",
        type: file.type || "unknown",
        size: file.size,
        sizeLabel: formatAttachmentSize(file.size),
        source,
      };

      if (!attachments.some((item) => item.id === attachment.id)) {
        attachments.push(attachment);
      }
    });

    renderAttachments();
    closeAttachmentMenu();
  }

  attachmentToggle?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!attachmentMenu || !attachmentToggle) return;
    const shouldOpen = attachmentMenu.hidden;
    attachmentMenu.hidden = !shouldOpen;
    attachmentToggle.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
  });

  filePicker?.addEventListener("click", () => fileInput?.click());
  imagePicker?.addEventListener("click", () => imageInput?.click());
  cameraPicker?.addEventListener("click", () => cameraInput?.click());

  fileInput?.addEventListener("change", (event) => {
    addAttachments(event.target.files, "local_file");
    event.target.value = "";
  });

  cameraInput?.addEventListener("change", (event) => {
    addAttachments(event.target.files, "camera");
    event.target.value = "";
  });

  imageInput?.addEventListener("change", (event) => {
    addAttachments(event.target.files, "image");
    event.target.value = "";
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    showToast(
      "واجهة React غير متاحة حالياً. أعد تحميل الصفحة ثم حاول مرة أخرى.",
      "error"
    );
  });
});

document.querySelectorAll("[data-file-search-form]").forEach((form) => {
  const fileInput = form.querySelector("[data-search-files]");
  const clearButton = form.querySelector("[data-clear-search-files]");
  const fileList = form.querySelector("[data-search-file-list]");
  const output = form.parentElement?.querySelector("[data-file-search-output]");
  let selectedFiles = [];

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
      });

      chip.append(text, removeButton);
      fileList.appendChild(chip);
    });
  }

  function highlightText(text, term) {
    const escapedText = escapeHtml(text);
    const escapedTerm = escapeHtml(term);

    if (!escapedTerm) return escapedText;

    return escapedText.replace(
      new RegExp(escapedTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"),
      (match) => `<mark class="search-highlight">${match}</mark>`
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
        <p>${highlightText(result.preview, term)}</p>
        ${result.pages.length ? `<span>الصفحات المطابقة: ${result.pages.map((page) => page.page).join(", ")}</span>` : ""}
      </article>
    `).join("");
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
    });
  });

  clearButton?.addEventListener("click", () => {
    selectedFiles = [];
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

    const results = [];

    for (const item of selectedFiles) {
      if (!item.parsed) continue;
      const { file, parsed } = item;
      const content = parsed.text;
      const matchIndex = content.toLowerCase().indexOf(term.toLowerCase());

      if (matchIndex >= 0) {
        const start = Math.max(0, matchIndex - 90);
        const end = Math.min(content.length, matchIndex + term.length + 140);
        results.push({
          fileName: file.name,
          fileType: parsed.extension.toUpperCase(),
          preview: content.slice(start, end).replace(/\s+/g, " ").trim(),
          pages: parsed.pages.filter((page) => page.text.toLowerCase().includes(term.toLowerCase())),
        });
      }
    }

    renderFileSearchResults(results, term);
    showToast(results.length ? "تم العثور على نتائج داخل الملفات." : "لا توجد نتيجة مطابقة.", results.length ? "success" : "error");
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
