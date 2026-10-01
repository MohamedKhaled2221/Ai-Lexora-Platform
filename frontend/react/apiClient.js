const win = typeof window !== "undefined" ? window : {};
const currentOrigin = typeof window !== "undefined" ? window.location?.origin : "";
const isLikelyDevServer = /^https?:\/\/(localhost|127\.0\.0\.1):(5500|5173|4173|3000|8080)$/.test(currentOrigin || "");
const inferredBackendApiBase = currentOrigin && !isLikelyDevServer ? currentOrigin : "http://localhost:50662";
const viteEnv = typeof import.meta !== "undefined" && import.meta && import.meta.env ? import.meta.env : {};
const configuredApiBase =
  win.LEXORA_API_BASE || viteEnv.VITE_LEXORA_API_BASE || inferredBackendApiBase;
export const API_BASE = configuredApiBase.replace(/\/$/, "");
const configuredM1ApiBase =
  win.LEXORA_M1_API_BASE || viteEnv.VITE_LEXORA_M1_API_BASE;
export const M1_API_BASE = (configuredM1ApiBase || "http://localhost:8001").replace(/\/$/, "");
const configuredPackage2ApiBase =
  win.LEXORA_PACKAGE2_API_BASE || viteEnv.VITE_LEXORA_PACKAGE2_API_BASE;
export const PACKAGE2_API_BASE = (configuredPackage2ApiBase || "http://localhost:8000").replace(/\/$/, "");
const ACCESS_TOKEN_KEY = "lexora-access-token";
const REFRESH_TOKEN_KEY = "lexora-refresh-token";
const USER_KEY = "lexora-user";

if (!win.LEXORA_API_BASE && !viteEnv.VITE_LEXORA_API_BASE) {
  console.info("Using inferred Lexora API base:", API_BASE);
}

function extractErrorMessage(payload, status) {
  const detail =
    payload?.error?.message ??
    payload?.message ??
    payload?.detail ??
    payload?.title;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || String(item))
      .join(", ");
  }

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  return `Request failed with status ${status}`;
}

export function getUserErrorMessage(error) {
  const messages = {
    400: "البيانات المرسلة غير صحيحة. راجع المدخلات وحاول مرة أخرى.",
    401: "انتهت الجلسة أو بيانات الدخول غير صحيحة. سجّل الدخول مرة أخرى.",
    403: "ليس لديك صلاحية لتنفيذ هذا الإجراء.",
    404: "العنصر المطلوب غير موجود.",
    409: "يوجد تعارض: قد تكون البيانات موجودة بالفعل.",
    413: "حجم الملف أكبر من الحد المسموح.",
    415: "نوع الملف غير مدعوم.",
    422: "تعذر استخراج محتوى صالح من الملف.",
    502: "الخدمة الوسيطة لم تستطع إكمال الطلب.",
    503: "الخدمة المطلوبة غير متاحة حاليًا. حاول مرة أخرى بعد قليل.",
  };
  return messages[error?.status] || error?.message || "حدث خطأ غير متوقع.";
}

async function parseResponse(response) {
  const text = await response.text();

  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    return {
      error: {
        message: "The server returned an invalid response.",
      },
    };
  }
}

function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

async function requestPackageApi(baseUrl, path, options = {}) {
  const headers = new Headers(options.headers || {});
  const isFormData = options.body instanceof FormData;

  if (!isFormData && options.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
  });
  const payload = await parseResponse(response);

  if (!response.ok) {
    const error = new Error(extractErrorMessage(payload, response.status));
    error.status = response.status;
    throw error;
  }

  return payload;
}

function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function storeAuthResponse(response) {
  localStorage.setItem(ACCESS_TOKEN_KEY, response.token);
  localStorage.setItem(REFRESH_TOKEN_KEY, response.refreshToken);
  localStorage.setItem(USER_KEY, JSON.stringify({
    email: response.email,
    fullName: response.fullName,
    role: response.role,
  }));
  window.dispatchEvent(new CustomEvent("lexora:auth-changed"));
  return response;
}

export function getSession() {
  return {
    accessToken: getAccessToken(),
    refreshToken: getRefreshToken(),
    user: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
  };
}

export function clearSession(redirect = true) {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new CustomEvent("lexora:auth-changed"));
  if (redirect && !window.location.pathname.endsWith("/auth.html")) {
    window.location.assign("/auth.html");
  }
}

function normalizeDocument(document) {
  return {
    ...document,
    id: String(document.id),
    fileName: document.fileName,
    sizeBytes: document.sizeBytes,
    status: document.status || "processed",
    localFileAvailable: false,
  };
}

async function refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });
  const payload = await parseResponse(response);
  if (!response.ok || !payload?.token || !payload?.refreshToken) return false;
  storeAuthResponse(payload);
  return true;
}

async function request(path, options = {}, allowRefresh = true) {
  const headers = new Headers(options.headers || {});
  const isFormData = options.body instanceof FormData;
  const accessToken = getAccessToken();

  if (!isFormData && options.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  const payload = await parseResponse(response);

  if (!response.ok) {
    if (response.status === 401 && allowRefresh && !path.startsWith("/api/auth/")) {
      const refreshed = await refreshAccessToken().catch(() => false);
      if (refreshed) return request(path, options, false);
      clearSession();
    }

    const error = new Error(getUserErrorMessage({
      status: response.status,
      message: extractErrorMessage(payload, response.status),
    }));

    error.status = response.status;
    error.code = payload?.error?.code;
    error.requestId =
      payload?.error?.request_id ??
      payload?.traceId;

    throw error;
  }

  return payload;
}

export async function requestApi(path, options = {}) {
  return request(path, options);
}

export async function checkBackendHealth() {
  const response = await fetch(`${API_BASE}/health`);
  const payload = await parseResponse(response);

  if (!response.ok) {
    const error = new Error(getUserErrorMessage({
      status: response.status,
      message: extractErrorMessage(payload, response.status),
    }));
    error.status = response.status;
    throw error;
  }

  return payload;
}

export async function getChatConversations() {
  return requestApi("/api/chatbot/conversations");
}

export async function createChatConversation() {
  return requestApi("/api/chatbot/conversations", { method: "POST" });
}

export async function getChatMessages(conversationId) {
  return requestApi(`/api/chatbot/conversations/${conversationId}/messages`);
}

export async function sendChatMessage(conversationId, content) {
  return requestApi(`/api/chatbot/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function getGeneratorTemplates() {
  return requestApi("/api/document-generator/templates");
}

export async function generateBackendDocument({ documentType, jurisdiction, fields, clauseLanguage, matterId }) {
  return requestApi("/api/document-generator/generate", {
    method: "POST",
    body: JSON.stringify({ documentType, jurisdiction, fields, clauseLanguage, matterId }),
  });
}

export async function downloadGeneratedExport(fileName) {
  if (!fileName) throw new TypeError("An export file name is required.");
  const path = `/api/document-generator/exports/${encodeURIComponent(fileName)}`;
  const send = () => fetch(`${API_BASE}${path}`, {
    headers: getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {},
  });

  let response = await send();
  if (response.status === 401 && await refreshAccessToken()) response = await send();
  if (!response.ok) {
    const payload = await parseResponse(response);
    const error = new Error(getUserErrorMessage({
      status: response.status,
      message: extractErrorMessage(payload, response.status),
    }));
    error.status = response.status;
    if (response.status === 401) clearSession();
    throw error;
  }

  const contentDisposition = response.headers.get("Content-Disposition") || "";
  const encodedName = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const quotedName = contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
  let responseFileName = encodedName || quotedName || fileName;
  try { responseFileName = decodeURIComponent(responseFileName); } catch { /* Use the header value as-is. */ }
  return { blob: await response.blob(), fileName: responseFileName };
}

export async function requestBackendApi(path, options = {}) {
  return requestApi(path, options);
}

export async function requestPackage1(path, options = {}) {
  return requestPackageApi(M1_API_BASE, path, options);
}

export async function requestPackage2(path, options = {}) {
  return requestPackageApi(PACKAGE2_API_BASE, path, options);
}

export function ingestPackage1(file, options = {}) {
  const formData = new FormData();
  formData.append("file", file);
  const query = new URLSearchParams(
    Object.entries(options).filter(([, value]) => value !== undefined && value !== null),
  );
  return requestPackage1(`/ingest${query.toString() ? `?${query}` : ""}`, {
    method: "POST",
    body: formData,
  });
}

export function extractClausesPackage1(file, options = {}) {
  const formData = new FormData();
  formData.append("file", file);
  const query = new URLSearchParams(
    Object.entries(options).filter(([, value]) => value !== undefined && value !== null),
  );
  return requestPackage1(`/clauses${query.toString() ? `?${query}` : ""}`, {
    method: "POST",
    body: formData,
  });
}

export function checkPackage1Health() {
  return requestPackage1("/health");
}

export function getPackage1Config() {
  return requestPackage1("/config");
}

export function ingestPackage1ThroughPackage2(file, documentId) {
  const formData = new FormData();
  formData.append("file", file);
  const query = documentId ? `?document_id=${encodeURIComponent(documentId)}` : "";
  return requestPackage2(`/api/v1/documents/ingest${query}`, {
    method: "POST",
    body: formData,
  });
}

export function askPackage2(question, filters = {}) {
  return requestPackage2("/api/v1/rag/ask", {
    method: "POST",
    body: JSON.stringify({ question, filters }),
  });
}

export function checkPackage2Health() {
  return requestPackage2("/health");
}

export function checkPackage2Readiness() {
  return requestPackage2("/ready");
}

export function answerPackage2(processedQuery, retrievedEvidence) {
  return requestPackage2("/api/v1/ai/answer", {
    method: "POST",
    body: JSON.stringify({ processed_query: processedQuery, retrieved_evidence: retrievedEvidence }),
  });
}

export function analyzePackage2Risk(clauses) {
  return requestPackage2("/api/v1/risk/analyze", {
    method: "POST",
    body: JSON.stringify({ clauses }),
  });
}

export async function login(email, password) {
  return storeAuthResponse(await request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  }, false));
}

export async function register(fullName, email, password) {
  return storeAuthResponse(await request("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ fullName, email, password }),
  }, false));
}

export async function resetPassword(email, token, newPassword) {
  return requestApi("/api/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ email, token, newPassword }),
  });
}

export async function confirmEmail(userId, token) {
  return requestApi("/api/auth/confirm-email", {
    method: "POST",
    body: JSON.stringify({ userId, token }),
  });
}

export async function resendEmailConfirmation(email) {
  return requestApi("/api/auth/resend-confirmation", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function requestEmailChange(newEmail, password) {
  return requestApi("/api/auth/change-email", {
    method: "POST",
    body: JSON.stringify({ newEmail, password }),
  });
}

export async function confirmEmailChange(userId, newEmail, token) {
  return requestApi("/api/auth/confirm-email-change", {
    method: "POST",
    body: JSON.stringify({ userId, newEmail, token }),
  });
}

export async function promoteUserToAdmin(email) {
  return requestApi("/api/auth/promote-to-admin", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function getProfile() {
  return requestApi("/api/profile");
}

export async function updateProfile(fullName) {
  return requestApi("/api/profile", {
    method: "PUT",
    body: JSON.stringify({ fullName }),
  });
}

export async function changeProfilePassword(currentPassword, newPassword) {
  return requestApi("/api/profile/password", {
    method: "PUT",
    body: JSON.stringify({ currentPassword, newPassword }),
  });
}

export async function listAdminUsers({ page = 1, pageSize = 20, search = "" } = {}) {
  const query = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
  if (search.trim()) query.set("search", search.trim());
  return requestApi(`/api/admin/users?${query.toString()}`);
}

export async function updateAdminUserRole(userId, role) {
  return requestApi(`/api/admin/users/${encodeURIComponent(userId)}/role`, {
    method: "PUT",
    body: JSON.stringify({ role }),
  });
}

export async function updateAdminUserStatus(userId, isActive) {
  return requestApi(`/api/admin/users/${encodeURIComponent(userId)}/status`, {
    method: "PUT",
    body: JSON.stringify({ isActive }),
  });
}

export async function setAdminUserAiScope(userId, clientId, confidentialityCeiling) {
  return requestApi(`/api/admin/users/${encodeURIComponent(userId)}/ai-scope`, {
    method: "PUT",
    body: JSON.stringify({ clientId, confidentialityCeiling }),
  });
}

export async function clearAdminUserAiScope(userId) {
  return requestApi(`/api/admin/users/${encodeURIComponent(userId)}/ai-scope`, {
    method: "DELETE",
  });
}

export async function logout() {
  try {
    if (getAccessToken()) {
      await request("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refreshToken: getRefreshToken() }),
      }, false);
    }
  } finally {
    clearSession(false);
  }
}

export async function uploadDocument(file, type = "Contract") {
  if (!(file instanceof File)) {
    throw new TypeError("A document file is required.");
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("type", type);

  const response = await requestApi("/api/documents", {
    method: "POST",
    body: formData,
  });

  return normalizeDocument(response);
}

export async function uploadDocumentsBatch(files, type = "Contract") {
  const selectedFiles = Array.from(files || []);
  if (selectedFiles.length < 1 || selectedFiles.length > 5) {
    throw new RangeError("Batch uploads require between 1 and 5 files.");
  }

  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("files", file));
  formData.append("type", type);

  const response = await requestApi("/api/documents/batch", {
    method: "POST",
    body: formData,
  });
  return (Array.isArray(response) ? response : []).map(normalizeDocument);
}

export async function getDocument(documentId) {
  return normalizeDocument(await requestApi(`/api/documents/${encodeURIComponent(documentId)}`));
}

export async function updateDocument(documentId, updates) {
  const body = {};
  if (updates.fileName !== undefined) body.fileName = updates.fileName;
  if (updates.type !== undefined) body.type = updates.type;
  return normalizeDocument(await requestApi(`/api/documents/${encodeURIComponent(documentId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  }));
}

export async function startContractAnalysis(documentId) {
  return requestApi(`/api/documents/${documentId}/analysis`, {
    method: "POST",
  });
}

export async function getContractAnalysis(documentId) {
  return requestApi(`/api/documents/${documentId}/analysis`);
}

export async function listDocuments() {
  const response = await requestApi("/api/documents?page=1&pageSize=100");
  const documents = Array.isArray(response?.items) ? response.items : [];
  return documents.map(normalizeDocument);
}

export async function downloadDocument(documentId) {
  let response = await fetch(`${API_BASE}/api/documents/${documentId}/download`, {
    headers: getAccessToken()
      ? { Authorization: `Bearer ${getAccessToken()}` }
      : {},
  });

  if (response.status === 401 && await refreshAccessToken()) {
    response = await fetch(`${API_BASE}/api/documents/${documentId}/download`, {
      headers: { Authorization: `Bearer ${getAccessToken()}` },
    });
  }

  if (!response.ok) {
    const payload = await parseResponse(response);
    const error = new Error(getUserErrorMessage({
      status: response.status,
      message: extractErrorMessage(payload, response.status),
    }));
    error.status = response.status;
    if (response.status === 401) clearSession();
    throw error;
  }

  return response.blob();
}

export async function deleteDocument(documentId) {
  await requestApi(`/api/documents/${documentId}`, { method: "DELETE" });
}

export async function askDocuments(question, documentIds = []) {
  const normalizedQuestion = question?.trim();

  if (!normalizedQuestion) {
    throw new Error("Question is required.");
  }
  if (normalizedQuestion.length > 4000) {
    const error = new Error("السؤال يجب ألا يتجاوز 4000 حرف.");
    error.status = 400;
    throw error;
  }

  // The .NET API derives the authorized document scope from the current user;
  // its request DTO intentionally accepts only the question.
  void documentIds;

  return requestApi("/api/search/ask", {
    method: "POST",
    body: JSON.stringify({
      question: normalizedQuestion,
    }),
  });
}

export async function generateContract(request) {
  return generateBackendDocument(request);
}

export async function reviewContract(contractText, action) {
  return askDocuments([
    action || "راجع هذا العقد",
    "حلل النص التالي وحدد الملاحظات القانونية العملية دون إعادة كتابة العقد كاملًا:",
    contractText,
  ].join("\n\n"));
}

// Temporary compatibility helper for the existing FastAPI widget.
// Step 6C removes its use from LegalAssistantWidget.
export function buildRawRagRequest(question, filters = {}) {
  return {
    question: question.trim(),
    ...filters,
  };
}