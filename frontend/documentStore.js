const STORAGE_KEY = "lexora-indexed-documents";

let state = {
  documents: readStoredDocuments(),
  selectedIds: [],
};

const listeners = new Set();

function readStoredDocuments() {
  try {
    const documents = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(documents)
      ? documents.map((document) => ({
          ...document,
          localFileAvailable: false,
          status: document.status === "indexed" ? "processed" : document.status || "processed",
        }))
      : [];
  } catch {
    return [];
  }
}

function emit() {
  listeners.forEach((listener) => listener());
}

function persistDocuments() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.documents));
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSnapshot() {
  return state;
}

export function refreshDocuments() {
  const documents = readStoredDocuments();
  const availableIds = new Set(documents.map((document) => document.id));
  state = {
    documents,
    selectedIds: state.selectedIds.filter((id) => availableIds.has(id)),
  };
  emit();
}

export function addProcessingDocument(document) {
  state = {
    ...state,
    documents: [
      document,
      ...state.documents.filter((item) => item.id !== document.id),
    ],
  };
  emit();
}

export function upsertDocument(document) {
  const normalizedDocument = {
    ...document,
    localFileAvailable: typeof File !== "undefined" && document.file instanceof File,
  };
  state = {
    ...state,
    documents: [
      normalizedDocument,
      ...state.documents.filter(
        (item) => item.id !== normalizedDocument.id && item.fileName !== normalizedDocument.fileName,
      ),
    ],
  };
  persistDocuments();
  emit();
}

export function removeDocument(documentId) {
  state = {
    documents: state.documents.filter((document) => document.id !== documentId),
    selectedIds: state.selectedIds.filter((id) => id !== documentId),
  };
  persistDocuments();
  emit();
}

export function setSelectedIds(selectedIds) {
  const availableIds = new Set(state.documents.map((document) => document.id));
  state = {
    ...state,
    selectedIds: [...new Set(selectedIds)].filter((id) => availableIds.has(id)),
  };
  emit();
}

export function toggleSelectedId(documentId, selected) {
  setSelectedIds(
    selected
      ? [...state.selectedIds, documentId]
      : state.selectedIds.filter((id) => id !== documentId),
  );
}
