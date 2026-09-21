import { demoCases, demoLawyers } from "./frontend/demoData.js";
import {
  API_BASE,
  getUserErrorMessage,
  login,
  logout,
  register,
  requestApi as requestBackendApi,
} from "./frontend/react/apiClient.js";

let documentParserPromise;

function loadDocumentParser() {
  documentParserPromise ||= import("./frontend/utils/documentParser.js");
  return documentParserPromise;
}

const toast = document.querySelector("[data-toast]");
const themeToggles = document.querySelectorAll("[data-theme-toggle]");

function setupNavbarMenu() {
  document.querySelectorAll(".navbar").forEach((navbar) => {
    if (navbar.dataset.navMenuReady === "true") return;

    const nav = navbar.querySelector("nav");
    if (!nav) return;

    const burgerButton = document.createElement("button");
    burgerButton.type = "button";
    burgerButton.className = "nav-burger";
    burgerButton.dataset.navBurger = "true";
    burgerButton.setAttribute("aria-label", "فتح قائمة التنقل");
    burgerButton.setAttribute("aria-expanded", "false");
    burgerButton.innerHTML = '<span></span><span></span><span></span>';
    navbar.appendChild(burgerButton);

    const backdrop = document.createElement("div");
    backdrop.className = "nav-backdrop";
    backdrop.hidden = true;
    document.body.appendChild(backdrop);

    const drawer = document.createElement("aside");
    drawer.className = "nav-drawer";
    drawer.setAttribute("aria-hidden", "true");
    drawer.innerHTML = `
      <div class="nav-drawer-header">
        <span>القائمة</span>
        <button type="button" class="nav-drawer-close" aria-label="إغلاق القائمة">×</button>
      </div>
      <div class="nav-drawer-content"></div>
    `;

    const drawerContent = drawer.querySelector(".nav-drawer-content");
    Array.from(nav.children).forEach((child) => {
      drawerContent.appendChild(child.cloneNode(true));
    });

    document.body.appendChild(drawer);

    const closeDrawer = () => {
      drawer.classList.remove("is-open");
      drawer.setAttribute("aria-hidden", "true");
      backdrop.classList.remove("is-visible");
      backdrop.hidden = true;
      burgerButton.setAttribute("aria-expanded", "false");
      document.body.classList.remove("nav-drawer-open");
    };

    const openDrawer = () => {
      drawer.classList.add("is-open");
      drawer.setAttribute("aria-hidden", "false");
      backdrop.hidden = false;
      window.requestAnimationFrame(() => backdrop.classList.add("is-visible"));
      burgerButton.setAttribute("aria-expanded", "true");
      document.body.classList.add("nav-drawer-open");
    };

    burgerButton.addEventListener("click", () => {
      const isOpen = drawer.classList.contains("is-open");
      if (isOpen) {
        closeDrawer();
      } else {
        openDrawer();
      }
    });

    backdrop.addEventListener("click", closeDrawer);
    drawer.querySelector(".nav-drawer-close")?.addEventListener("click", closeDrawer);
    drawer.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", closeDrawer);
    });

    navbar.dataset.navMenuReady = "true";
  });
}

function setupAccountControls() {
  document.querySelectorAll(".auth-nav-link").forEach((link) => {
    if (link.closest(".account-menu-wrap")) return;

    const wrapper = document.createElement("div");
    wrapper.className = "account-menu-wrap";
    link.parentNode.insertBefore(wrapper, link);
    wrapper.appendChild(link);

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "account-menu-trigger";
    if (link.classList.contains("active")) trigger.classList.add("active");
    trigger.setAttribute("aria-label", "فتح قائمة الحساب");
    trigger.setAttribute("aria-expanded", "false");
    trigger.title = "الحساب";
    trigger.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.25" /><path d="M5.5 20a6.5 6.5 0 0 1 13 0" /></svg>';
    link.replaceWith(trigger);

    const menu = document.createElement("div");
    menu.className = "account-menu";
    menu.hidden = true;
    menu.innerHTML = `
      <a href="auth.html"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" /><path d="m10 17 5-5-5-5M15 12H3" /></svg><span>تسجيل الدخول</span></a>
      <a href="auth.html#register"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="4" /><path d="M3 21a6 6 0 0 1 12 0M19 8v6M16 11h6" /></svg><span>إنشاء حساب جديد</span></a>
    `;
    wrapper.appendChild(menu);

    const closeMenu = () => {
      menu.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      wrapper.classList.remove("is-open");
    };

    trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = !menu.hidden;
      document.querySelectorAll(".account-menu").forEach((item) => { item.hidden = true; });
      document.querySelectorAll(".account-menu-trigger").forEach((item) => { item.setAttribute("aria-expanded", "false"); });
      menu.hidden = isOpen;
      trigger.setAttribute("aria-expanded", String(!isOpen));
      wrapper.classList.toggle("is-open", !isOpen);
    });

    menu.addEventListener("click", (event) => event.stopPropagation());
    menu.querySelectorAll("a").forEach((item) => item.addEventListener("click", closeMenu));
    trigger.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
      if (event.key === "ArrowDown") {
        event.preventDefault();
        menu.hidden = false;
        trigger.setAttribute("aria-expanded", "true");
        menu.querySelector("a")?.focus();
      }
    });

    wrapper.accountMenuClose = closeMenu;

    const tools = wrapper.closest(".navbar")?.querySelector(".nav-tools");
    const primaryAction = tools?.querySelector(".nav-action");
    if (tools && primaryAction) tools.insertBefore(wrapper, primaryAction);
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest(".account-menu-wrap")) return;
    document.querySelectorAll(".account-menu-wrap").forEach((wrapper) => wrapper.accountMenuClose?.());
  });
}

function setupPasswordVisibilityToggles() {
  document.querySelectorAll(".password-toggle-btn").forEach((button) => {
    const field = button.closest(".password-field");
    const input = field?.querySelector("input");

    if (!field || !input) return;

    const syncButtonState = () => {
      const isVisible = input.type === "text";
      button.classList.toggle("is-visible", isVisible);
      button.setAttribute("aria-label", isVisible ? "إخفاء كلمة المرور" : "إظهار كلمة المرور");
      button.setAttribute("aria-pressed", String(isVisible));
      button.title = isVisible ? "إخفاء كلمة المرور" : "إظهار كلمة المرور";
    };

    button.addEventListener("click", () => {
      input.type = input.type === "password" ? "text" : "password";
      syncButtonState();
      input.focus();
      const end = input.value.length;
      input.setSelectionRange(end, end);
    });

    syncButtonState();
  });
}

function setupDashboardSidebarDrawer() {
  const layout = document.querySelector(".app-layout");
  const sidebar = document.querySelector(".sidebar");
  const toggle = document.querySelector(".dashboard-sidebar-toggle");

  if (!layout || !sidebar || !toggle || sidebar.dataset.drawerReady === "true") {
    return;
  }

  layout.classList.add("dashboard-sidebar-mode");
  sidebar.classList.add("dashboard-sidebar-drawer");
  sidebar.dataset.drawerReady = "true";

  const backdrop = document.createElement("div");
  backdrop.className = "dashboard-sidebar-backdrop";
  backdrop.hidden = true;
  document.body.appendChild(backdrop);

  const closeSidebar = () => {
    sidebar.classList.remove("is-open");
    backdrop.classList.remove("is-visible");
    backdrop.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("dashboard-sidebar-open");
  };

  const openSidebar = () => {
    sidebar.classList.add("is-open");
    backdrop.hidden = false;
    window.requestAnimationFrame(() => backdrop.classList.add("is-visible"));
    toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("dashboard-sidebar-open");
  };

  toggle.addEventListener("click", () => {
    const isOpen = sidebar.classList.contains("is-open");
    if (isOpen) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });

  backdrop.addEventListener("click", closeSidebar);
  sidebar.querySelectorAll("a, button").forEach((item) => {
    item.addEventListener("click", closeSidebar);
  });
}

function setupConsultationAiComposer() {
  const trigger = document.querySelector(".consultation-ai-plus");
  const menu = document.querySelector(".consultation-ai-menu");

  if (!trigger || !menu) return;

  const closeMenu = () => {
    menu.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  };

  const openMenu = () => {
    menu.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
  };

  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (menu.hidden) {
      openMenu();
    } else {
      closeMenu();
    }
  });

  menu.querySelectorAll("button[data-ai-file-target]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();

      const targetId = button.dataset.aiFileTarget;
      const input = document.getElementById(targetId);

      closeMenu();

      if (input) {
        input.value = "";
        window.setTimeout(() => input.click(), 0);
      }
    });
  });

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!menu.contains(target) && target !== trigger && !trigger.contains(target)) {
      closeMenu();
    }
  });
}

function updateNavbarMode() {
  const compactMode = window.scrollY > 28;

  document.querySelectorAll(".navbar").forEach((navbar) => {
    navbar.classList.toggle("navbar--compact", compactMode);
  });
}

setupNavbarMenu();
setupAccountControls();
setupPasswordVisibilityToggles();
setupConsultationAiComposer();
setupDashboardSidebarDrawer();
updateNavbarMode();
window.addEventListener("scroll", updateNavbarMode, { passive: true });
window.addEventListener("resize", updateNavbarMode);

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
    const track = toggle.querySelector(".theme-toggle-track");
    if (label) label.textContent = theme === "dark" ? "الوضع الفاتح" : "الوضع الغامق";
    toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    toggle.setAttribute("title", theme === "dark" ? "تفعيل الوضع الفاتح" : "تفعيل الوضع الغامق");
    if (track) {
      track.innerHTML = theme === "dark"
        ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5 8.5 8.5 0 1 0 20.5 14.5Z" /></svg>'
        : '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" /></svg>';
    }
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

const requestApi = requestBackendApi;

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
      renderJson(output, { error: error.message, apiBase: API_BASE, endpoint: "/health" });
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
      const payload = await requestApi("/health");
      renderJson(output, payload);
      const ready = payload.status === "ok";
      setStatusCard(
        card,
        ready ? "ready" : "error",
        ready ? "جاهز" : "يحتاج مراجعة",
        payload.dependencies
          ? "تم فحص قاعدة البيانات وخدمات Backend التابعة."
          : "تعذر تأكيد حالة Backend."
      );
      showToast(ready ? "النظام جاهز." : "النظام يحتاج مراجعة.", ready ? "success" : "error");
    } catch (error) {
      setStatusCard(card, "error", "غير جاهز", error.message);
      renderJson(output, { error: error.message, apiBase: API_BASE, endpoint: "/health" });
      showToast("فحص الجاهزية فشل.", "error");
    } finally {
      button.disabled = false;
    }
  });
});


document.querySelectorAll("form:not([data-file-search-form]):not([data-auth-panel])").forEach((form) => {
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

document.querySelectorAll("form[data-auth-panel]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) {
      form.classList.add("was-validated");
      return;
    }

    const submitButton = form.querySelector("button[type=submit]");
    submitButton.disabled = true;
    const panel = form.dataset.authPanel;

    try {
      if (panel === "login") {
        await login(
          form.querySelector("#login-email").value.trim(),
          form.querySelector("#login-password").value,
        );
        showToast("تم تسجيل الدخول بنجاح.", "success");
        window.setTimeout(() => window.location.assign("/dashboard.html"), 350);
      } else if (panel === "register") {
        await register(
          form.querySelector("#register-name").value.trim(),
          form.querySelector("#register-email").value.trim(),
          form.querySelector("#register-password").value,
        );
        showToast("تم إنشاء الحساب وتسجيل الدخول.", "success");
        window.setTimeout(() => window.location.assign("/dashboard.html"), 350);
      } else if (panel === "forgot") {
        await requestApi("/api/auth/forgot-password", {
          method: "POST",
          body: JSON.stringify({ email: form.querySelector("#forgot-email").value.trim() }),
        });
        showToast("تم إرسال طلب استعادة كلمة المرور.", "success");
        form.reset();
      }
    } catch (error) {
      showToast(getUserErrorMessage(error), "error");
    } finally {
      submitButton.disabled = false;
    }
  });
});

document.querySelectorAll("[data-logout]").forEach((button) => {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await logout();
      showToast("تم تسجيل الخروج.", "success");
      window.location.assign("/auth.html");
    } catch (error) {
      showToast(getUserErrorMessage(error), "error");
      button.disabled = false;
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
    create: "إضافة قضية جديدة",
    view: "عرض بيانات القضية",
    edit: "تعديل القضية",
    assign: "تعيين محامٍ",
  };
  const contexts = {
    create: "هذه نسخة عرض محلية، والبيانات ستظهر فقط داخل الجلسة الحالية للمستخدم.",
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
    modalSecondary.textContent = "إغلاق القضية";
  }
  Object.entries(modalFields).forEach(([field, input]) => {
    if (!input) return;
    input.disabled = isView || (isAssign && !["lawyer"].includes(field));
  });
  if (modal) {
    modal.hidden = false;
    document.body.classList.add("modal-open");
    window.setTimeout(() => (isView ? modalFields.title : modalFields.id)?.focus(), 0);
  }
}

function openCaseModal(mode, item = null, trigger = null) {
  setModalMode(mode, item, trigger);
}

function closeCaseModal() {
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
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
      showToast("رقم القضية مستخدم بالفعل في العرض المحلي.", "error");
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
    showToast("تمت إضافة القضية داخل العرض المحلي فقط.", "info");
    return;
  }

  const item = dashboardCases.find((candidate) => candidate.id === modalCaseId);
  if (!item) return;
  Object.assign(item, values);
  renderCaseRows();
  applyTableFilters();
  closeCaseModal();
  showToast(modalMode === "assign" ? "تم تحديث المحامي داخل العرض المحلي فقط." : "تم تحديث القضية داخل العرض المحلي فقط.", "info");
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
