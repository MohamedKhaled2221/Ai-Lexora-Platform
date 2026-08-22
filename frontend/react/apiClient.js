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
  const payload = text ? JSON.parse(text) : {};

  if (!response.ok) {
    const detail = payload.detail || `Request failed with status ${response.status}`;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join(", ")
      : detail;

    throw new Error(message);
  }

  return payload;
}

export function buildProcessedQuery(text, language = "ar") {
  const normalizedText = text.trim();

  return {
    query_id: `q_front_${Date.now()}`,
    text_original: text,
    normalized_text: normalizedText,
    language,
    embedding: [],
    sparse_embedding: null,
    filters: {
      document_type: null,
      jurisdiction: "Egypt",
      language: null,
      extra_filters: {},
    },
    query_variants: [normalizedText],
    identifiers: {
      article_numbers: [],
      case_numbers: [],
      dates: [],
      monetary_values: [],
      party_names: [],
    },
  };
}

export function buildDemoEvidence(queryId) {
  return {
    query_id: queryId,
    retrieved_evidence: [
      {
        document_id: "demo_contract_001",
        chunk_id: "chunk_12",
        text: "Contract termination requires prior written notice and a reasonable cure period.",
        page: 4,
        section: "Termination clause",
        language: "en",
        score: 0.92,
      },
      {
        document_id: "demo_labor_002",
        chunk_id: "chunk_07",
        text: "Penalties and notice duties should be grounded in the contract and applicable law.",
        page: 9,
        section: "Duties",
        language: "en",
        score: 0.81,
      },
    ],
  };
}
