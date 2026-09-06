export const AI_API_BASE =
  window.AI_LEXORA_API_BASE || "http://127.0.0.1:8000";

// Temporary compatibility alias.
// Existing React components still use API_BASE until Step 6C.
export const API_BASE = AI_API_BASE;
const DOCUMENTS_STORAGE_KEY = "lexora-indexed-documents";

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

export async function requestApi(path, options = {}) {
  return request(AI_API_BASE, path, options);
}

export async function requestBackendApi(path, options = {}) {
  return requestApi(path, options);
}

export async function uploadDocument(file, type = "Contract") {
  if (!(file instanceof File)) {
    throw new TypeError("A document file is required.");
  }

  const formData = new FormData();
  formData.append("file", file);

  const response = await requestApi("/api/v1/documents/ingest", {
    method: "POST",
    body: formData,
  });

  const document = {
    id: response.document_id,
    fileName: response.source_file || file.name,
    sizeBytes: file.size,
    ...response,
  };

  const documents = await listDocuments();
  localStorage.setItem(
    DOCUMENTS_STORAGE_KEY,
    JSON.stringify([
      document,
      ...documents.filter((item) => item.id !== document.id),
    ]),
  );

  return document;
}

export async function listDocuments() {
  try {
    const documents = JSON.parse(
      localStorage.getItem(DOCUMENTS_STORAGE_KEY) || "[]",
    );
    return Array.isArray(documents) ? documents : [];
  } catch {
    return [];
  }
}

export async function askDocuments(question, documentIds = []) {
  const normalizedQuestion = question?.trim();

  if (!normalizedQuestion) {
    throw new Error("Question is required.");
  }

  return requestApi("/api/v1/rag/ask", {
    method: "POST",
    body: JSON.stringify({
      question: normalizedQuestion,
      filters: {
        document_ids: documentIds,
        jurisdiction: "Egypt",
      },
    }),
  });
}

export async function generateContract(request) {
  const data = request?.contractData || {};
  const prompt = [
    "اكتب مسودة عقد قانونية باللغة المناسبة للبيانات التالية.",
    `نوع العقد: ${request?.contractType || "غير محدد"}`,
    `القالب: ${request?.template || "غير محدد"}`,
    `البيانات: ${JSON.stringify(data)}`,
    `تعليمات إضافية: ${request?.additionalInstructions || "لا توجد"}`,
    "أخرج نص العقد فقط مع عناوين واضحة، واذكر أن الناتج مسودة تحتاج مراجعة قانونية.",
  ].join("\n");

  return askDocuments(prompt);
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
    filters: {
      document_type: filters.document_type || null,
      jurisdiction: filters.jurisdiction || "Egypt",
      language: filters.language || null,
      extra_filters: {},
    },
  };
}