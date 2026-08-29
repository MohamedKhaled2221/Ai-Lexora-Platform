export const API_BASE = window.AI_LEXORA_API_BASE || "http://localhost:8000";

export async function requestApi(path, options = {}) {
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
    payload = { error: { message: text || "The server returned an invalid response." } };
  }

  if (!response.ok) {
    const detail = payload.error?.message || payload.detail || `Request failed with status ${response.status}`;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || item.message).join(", ")
      : detail;

    const error = new Error(message);
    error.code = payload.error?.code;
    error.requestId = payload.error?.request_id;
    throw error;
  }

  return payload;
}

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

