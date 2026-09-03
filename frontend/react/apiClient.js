export const AI_API_BASE =
  window.AI_LEXORA_API_BASE || "http://127.0.0.1:8000";

export const BACKEND_API_BASE =
  window.LEXORA_BACKEND_API_BASE || "http://127.0.0.1:5080";

// Temporary compatibility alias.
// Existing React components still use API_BASE until Step 6C.
export const API_BASE = AI_API_BASE;

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

async function request(baseUrl, path, options = {}) {
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
    const error = new Error(
      extractErrorMessage(payload, response.status),
    );

    error.status = response.status;
    error.code = payload?.error?.code;
    error.requestId =
      payload?.error?.request_id ??
      payload?.traceId;

    throw error;
  }

  return payload;
}

// Existing FastAPI client.
// Kept temporarily so Step 6B does not break the current UI.
// We will remove direct browser -> FastAPI usage after the React
// Package 1 flow has been migrated.
export async function requestApi(path, options = {}) {
  return request(AI_API_BASE, path, options);
}

function getBackendAccessToken() {
  const token = window.LEXORA_ACCESS_TOKEN;

  return typeof token === "string"
    ? token.trim()
    : "";
}

export async function requestBackendApi(path, options = {}) {
  const token = getBackendAccessToken();

  if (!token) {
    const error = new Error(
      "An authenticated backend access token is required.",
    );

    error.status = 401;
    throw error;
  }

  const headers = new Headers(options.headers || {});

  if (!headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return request(BACKEND_API_BASE, path, {
    ...options,
    headers,
  });
}

export async function uploadDocument(file, type = "Contract") {
  if (!(file instanceof File)) {
    throw new TypeError("A document file is required.");
  }

  const formData = new FormData();
  formData.append("file", file);

  if (type) {
    formData.append("type", type);
  }

  return requestBackendApi("/api/documents", {
    method: "POST",
    body: formData,
  });
}

export async function listDocuments() {
  const response = await requestBackendApi(
    "/api/documents?page=1&pageSize=100",
  );

  return Array.isArray(response.items)
    ? response.items
    : [];
}

export async function askDocuments(question) {
    const normalizedQuestion = question?.trim();

    if (!normalizedQuestion) {
      throw new Error("Question is required.");
    }

    return requestBackendApi("/api/search/ask", {
      method: "POST",
      body: JSON.stringify({
        question: normalizedQuestion,
      }),
    });
  }

// Temporary compatibility helper for the existing FastAPI widget.
// Step 6C removes its use from LegalAssistantWidget.
export function buildRawRagRequest(question, filters = {}) {
  return {
    question: question.trim(),
    filters: {
      document_type: filters.document_type || null,
      jurisdiction: filters.jurisdiction || "Egypt",
      language: filters.language || null,
      extra_filters: {},
    },
  };
}