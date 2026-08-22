const toast = document.querySelector("[data-toast]");

function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2200);
}

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    form.classList.add("was-validated");
    if (form.checkValidity()) {
      showToast("تم تنفيذ العملية بنجاح.");
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
    showToast("تم حفظ التعديل بنجاح.");
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

function applyRoleView() {
  const role = getSelectedRole();

  document.querySelectorAll("[data-role-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.rolePanel !== role;
  });

  document.querySelectorAll("[data-nav-lawyer]").forEach((item) => {
    item.hidden = role !== "lawyer";
  });

  document.querySelectorAll("[data-nav-manager]").forEach((item) => {
    item.hidden = role !== "manager";
  });

  document.querySelectorAll("[data-manager-only]").forEach((item) => {
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

searchInput?.addEventListener("input", applyTableFilters);
filterSelect?.addEventListener("change", applyTableFilters);
roleSwitch?.addEventListener("change", applyRoleView);

document.querySelector("[data-sort]")?.addEventListener("click", () => {
  if (!tableBody) return;
  const rows = Array.from(tableBody.querySelectorAll("tr"));
  rows
    .sort((a, b) => a.children[2].textContent.localeCompare(b.children[2].textContent, "ar"))
    .forEach((row) => tableBody.appendChild(row));
  applyTableFilters();
  showToast("تم ترتيب الجدول أبجديا.");
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
    showToast(button.dataset.showToast);
  });
});

applyRoleView();

