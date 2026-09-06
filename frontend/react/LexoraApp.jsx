import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  askDocuments,
  requestApi,
  uploadDocument,
} from "./apiClient.js";
import { documentActionLabels, documentStatusLabels } from "../documentDemoData.js";
import {
  addProcessingDocument,
  getSnapshot,
  refreshDocuments as refreshDocumentStore,
  removeDocument as removeStoredDocument,
  setSelectedIds,
  subscribe,
  toggleSelectedId,
  upsertDocument,
} from "../documentStore.js";
import { demoCases, demoLawyers } from "../demoData.js";

function StatusPill({ state, children }) {
  return (
    <span className={`react-pill ${state}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}

function formatFileSize(size) {
  if (!size) return "0 KB";
  if (size < 1024 * 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function ErrorState({ error, onRetry }) {
  return (
    <div className="agent-error" role="alert">
      <strong>تعذر تنفيذ الطلب</strong>
      <p>{error?.message || "تحقق من السؤال وحاول مرة أخرى."}</p>
      {error.requestId ? <small>رقم الطلب: {error.requestId}</small> : null}
      <button className="ghost-btn" type="button" onClick={onRetry}>إعادة المحاولة</button>
    </div>
  );
}

function CitationList({ citations }) {
  if (!citations.length) {
    return (
      <p className="empty-result citation-empty">
        لم تُرجع الخدمة مراجع قابلة للعرض لهذا السؤال.
      </p>
    );
  }

  return (
    <div className="citation-list">
      {citations.map((citation) => {
        const evidenceId = citation.evidence_id ?? citation.evidenceId;
        const documentId = citation.document_id ?? citation.documentId;
        const chunkId = citation.chunk_id ?? citation.chunkId;

        return (
        <article
          className="citation-card"
          key={`${evidenceId}-${documentId}-${chunkId}`}
        >
          <strong>
            {evidenceId} - {documentId}
          </strong>

          <span>
            المستند: #{documentId}
          </span>

          <span>
            المقطع: {chunkId}
          </span>

          {citation.page !== null &&
          citation.page !== undefined ? (
            <span>
              الصفحة: {citation.page}
            </span>
          ) : null}

          {citation.section ? (
            <span>
              القسم: {citation.section}
            </span>
          ) : null}
          <small className="citation-unavailable">
            فتح المستند والمعاينة غير متاحين حاليًا من الواجهة.
          </small>
        </article>
        );
      })}
    </div>
  );
}

export function BackendStatusWidget() {
  const [result, setResult] = useState({
    status: "waiting",
  });
  const [loading, setLoading] = useState("");

  async function check(path) {
    setLoading(path);
    setResult({ status: "loading", endpoint: path });

    try {
      const payload = await requestApi(path);
      setResult(payload);
    } catch (error) {
      setResult({
        status: "error",
        endpoint: path,
        message: "تعذر الاتصال بالخدمة حاليًا. حاول مرة أخرى بعد قليل.",
      });
    } finally {
      setLoading("");
    }
  }

  const isReady = result.status === "ready" || result.status === "ok";
  const isError = result.status === "error" || result.status === "not_ready";

  return (
    <div className="react-widget">
      <div className="table-header">
        <div>
          <p className="eyebrow">حالة الخدمات</p>
          <h2>متابعة جاهزية النظام</h2>
          <p>تحقق من اتصال الخدمات قبل بدء العمل على القضايا والمستندات.</p>
        </div>
        <StatusPill state={isReady ? "ready" : isError ? "error" : "idle"}>
          {isReady ? "جاهز" : isError ? "يحتاج مراجعة" : "بانتظار الفحص"}
        </StatusPill>
      </div>

      <div className="quick-actions">
        <button
          className="ghost-btn"
          type="button"
          disabled={loading === "/health"}
          onClick={() => check("/health")}
        >
          فحص التشغيل
        </button>
        <button
          className="primary-btn"
          type="button"
          disabled={loading === "/ready"}
          onClick={() => check("/ready")}
        >
          فحص الجاهزية
        </button>
      </div>

      <div className={`service-status-message ${isError ? "error" : isReady ? "ready" : "idle"}`} role="status">
        <strong>
          {result.status === "loading"
            ? "جاري التحقق من الخدمة..."
            : isReady
              ? "الخدمة متصلة وجاهزة للعمل."
              : isError
                ? "الخدمة تحتاج إلى مراجعة الاتصال."
                : "لم يتم التحقق من حالة الخدمة بعد."}
        </strong>
        {result.message ? <span>{result.message}</span> : null}
      </div>
    </div>
  );
}

export function CaseInsightsWidget() {
  const [selectedLawyer, setSelectedLawyer] = useState("all");

  const filteredCases = useMemo(() => {
    if (selectedLawyer === "all") return demoCases;
    return demoCases.filter((item) => item.lawyer === selectedLawyer);
  }, [selectedLawyer]);

  const urgentCount = filteredCases.filter((item) => item.status === "عاجلة").length;
  const activeCount = filteredCases.filter((item) => item.status === "نشطة").length;
  const lawyers = ["all", ...demoLawyers];

  return (
    <section className="api-section react-widget">
      <div className="table-header">
        <div>
          <p className="eyebrow">React Insights</p>
          <h2>ملخص ذكي للقضايا</h2>
          <p>فلترة سريعة وتحليل بسيط للقضايا المعروضة في لوحة العمل.</p>
        </div>
        <label className="role-switch">
          المحامي
          <select value={selectedLawyer} onChange={(event) => setSelectedLawyer(event.target.value)}>
            {lawyers.map((lawyer) => (
              <option value={lawyer} key={lawyer}>
                {lawyer === "all" ? "كل المحامين" : lawyer}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="react-insight-grid">
        <article className="status-card">
          <strong>{filteredCases.length}</strong>
          <span>قضية في النطاق الحالي</span>
        </article>
        <article className="status-card">
          <strong>{activeCount}</strong>
          <span>قضايا نشطة</span>
        </article>
        <article className="status-card">
          <strong>{urgentCount}</strong>
          <span>قضايا عاجلة</span>
        </article>
      </div>

      <div className="react-case-list">
        {filteredCases.map((item) => (
          <article className="react-case-item" key={item.id}>
            <strong>{item.id}</strong>
            <span>{item.title}</span>
            <small>{item.client} - {item.deadline}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function documentTypeLabel(fileName = "") {
  const extension = fileName.split(".").pop()?.toUpperCase();
  return extension || "FILE";
}

function documentStatusLabel(status) {
  return documentStatusLabels[status] || status || "غير معروف";
}

export function DocumentLibraryWidget() {
  const { documents, selectedIds } = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [previewDocument, setPreviewDocument] = useState(null);
  const fileInputRef = useRef(null);
  const previewCloseRef = useRef(null);
  const previewTriggerRef = useRef(null);

  async function refreshDocuments() {
    setLoading(true);
    setError("");

    try {
      refreshDocumentStore();
    } catch {
      setError("تعذر تحميل قائمة المستندات المحلية.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshDocuments();
  }, []);

  useEffect(() => {
    if (!previewDocument) return undefined;
    previewCloseRef.current?.focus();

    function handlePreviewKeyDown(event) {
      if (event.key === "Escape") {
        setPreviewDocument(null);
        previewTriggerRef.current?.focus();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        document.querySelectorAll(".document-preview button:not([disabled])"),
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
    }

    document.addEventListener("keydown", handlePreviewKeyDown);
    return () => document.removeEventListener("keydown", handlePreviewKeyDown);
  }, [previewDocument]);

  function updateSelection(documentId, checked) {
    toggleSelectedId(documentId, checked);
  }

  async function uploadFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    setUploading(true);
    setError("");

    for (const file of files) {
      const processingId = `processing_${file.name}_${file.lastModified}_${file.size}`;
      addProcessingDocument({
        id: processingId,
        fileName: file.name,
        sizeBytes: file.size,
        status: "processing",
        file,
      });

      try {
        const uploaded = await uploadDocument(file, "Contract");
        upsertDocument({ ...uploaded, status: "processed", file });
      } catch (uploadError) {
        upsertDocument({
          id: processingId,
          fileName: file.name,
          sizeBytes: file.size,
          status: "failed",
          error: uploadError?.message || "تعذرت معالجة المستند.",
          file,
        });
      }
    }

    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeDocument(documentId) {
    removeStoredDocument(documentId);
  }

  function downloadDocument(document) {
    if (!(document.file instanceof File)) return;
    const url = URL.createObjectURL(document.file);
    const link = window.document.createElement("a");
    link.href = url;
    link.download = document.fileName;
    link.click();
    URL.revokeObjectURL(url);
  }

  function handleDocumentAction(action, document, trigger = null) {
    if (action === "preview") {
      previewTriggerRef.current = trigger;
      setPreviewDocument(document);
      return;
    }
    if (action === "download") {
      downloadDocument(document);
      return;
    }
    if (action === "delete") {
      removeDocument(document.id);
      return;
    }
    if (action === "link") {
      setError("ربط المستند بالقضية غير متاح حاليًا، وتم إبقاءه كإجراء تجريبي فقط.");
    }
  }

  function retryDocument(document) {
    if (document.file) void uploadFiles([document.file]);
    else setError("لا توجد نسخة محلية من الملف لإعادة المحاولة.");
  }

  return (
    <div className="document-library" aria-live="polite">
      <div className="document-toolbar">
        <div>
          <strong>مكتبة المستندات</strong>
          <small>{selectedIds.length} مستند محدد للبحث لاحقًا</small>
        </div>
        <div className="document-toolbar-actions">
          <input
            ref={fileInputRef}
            className="visually-hidden"
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
            onChange={(event) => void uploadFiles(event.target.files)}
          />
          <button className="primary-btn" type="button" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
            {uploading ? "جاري المعالجة..." : "رفع مستند"}
          </button>
        </div>
      </div>

      {loading ? <div className="document-state" data-state="loading">جاري تحميل المستندات...</div> : null}
      {error ? <div className="document-state" data-state="error" role="alert"><strong>{error}</strong><button className="ghost-btn" type="button" onClick={() => void refreshDocuments()}>إعادة المحاولة</button></div> : null}
      {!loading && !error && !documents.length ? (
        <div className="document-state" data-state="empty">
          <strong>لا توجد مستندات في هذه الجلسة.</strong>
          <span>ارفع ملفًا لبدء المعالجة. لن تظهر نتيجة ناجحة إلا بعد اكتمال الرفع الفعلي.</span>
        </div>
      ) : null}

      <div className="document-grid">
        {documents.map((document) => (
          <article className={`document-card document-card-${document.status}`} key={document.id}>
            <div className="document-card-heading">
              <label className="document-select" title="تحديد المستند للبحث">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(document.id)}
                  onChange={(event) => updateSelection(document.id, event.target.checked)}
                  disabled={document.status !== "processed" || !document.localFileAvailable}
                />
                <span>تحديد</span>
              </label>
              <span className={`document-status status-${document.status}`}>
                {document.status === "processed" && !document.localFileAvailable ? "بيانات محفوظة محليًا" : documentStatusLabel(document.status)}
              </span>
            </div>
            <strong className="document-name">{document.fileName || "مستند بدون اسم"}</strong>
            <div className="document-meta">
              <span>{documentTypeLabel(document.fileName)}</span>
              <span>{formatFileSize(document.sizeBytes)}</span>
              {document.document_id || document.id ? <span title="معرف المستند">ID: {document.document_id || document.id}</span> : null}
            </div>
            {document.status === "processing" ? <p className="document-detail">يتم رفع الملف وفهرسته الآن.</p> : null}
            {document.status === "failed" ? <p className="document-detail document-error">{document.error}</p> : null}
            {document.status === "processed" && document.localFileAvailable ? <p className="document-detail">جاهز للاختيار في البحث، والإجراءات الإضافية محلية.</p> : null}
            {document.status === "processed" && !document.localFileAvailable ? <p className="document-detail document-local-unavailable">بيانات المستند محفوظة محليًا، لكن الملف الأصلي غير متاح بعد إعادة تحميل الصفحة. ارفع الملف مجددًا للمعاينة أو البحث أو التنزيل.</p> : null}
            <div className="document-actions">
              {document.status === "failed" ? <button className="ghost-btn" type="button" onClick={() => retryDocument(document)}>{documentActionLabels.retry}</button> : null}
              {document.status === "processed" && document.localFileAvailable ? <>
                <button className="ghost-btn" type="button" onClick={(event) => handleDocumentAction("preview", document, event.currentTarget)}>{documentActionLabels.preview}</button>
                <button className="ghost-btn" type="button" onClick={() => handleDocumentAction("download", document)}>{documentActionLabels.download}</button>
                <button className="ghost-btn" type="button" onClick={() => handleDocumentAction("link", document)}>{documentActionLabels.link}</button>
              </> : null}
              {document.status === "processed" && !document.localFileAvailable ? <button className="ghost-btn" type="button" onClick={() => fileInputRef.current?.click()}>رفع الملف مجددًا</button> : null}
              <button className="icon-btn" type="button" aria-label={`إزالة ${document.fileName || "المستند"}`} onClick={() => handleDocumentAction("delete", document)}>×</button>
            </div>
          </article>
        ))}
      </div>

      {previewDocument ? (
        <div className="document-preview" role="dialog" aria-modal="true" aria-labelledby="document-preview-title" aria-describedby="document-preview-description">
          <div className="document-preview-box">
            <div className="modal-header"><h3 id="document-preview-title">معاينة محلية</h3><button ref={previewCloseRef} className="icon-btn" type="button" aria-label="إغلاق المعاينة" onClick={() => { setPreviewDocument(null); previewTriggerRef.current?.focus(); }}>×</button></div>
            <strong>{previewDocument.fileName}</strong>
            <p id="document-preview-description">{previewDocument.file instanceof File ? "هذه معاينة محلية للملف المختار فقط." : "لا توجد نسخة محلية للمعاينة بعد إعادة تحميل الصفحة."}</p>
            <button className="ghost-btn" type="button" onClick={() => { setPreviewDocument(null); previewTriggerRef.current?.focus(); }}>إغلاق</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function LegalAssistantWidget({ mode = "ai" }) {
  const [question, setQuestion] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [result, setResult] = useState({ status: "waiting" });
  const [loading, setLoading] = useState(false);
  const [lastQuestion, setLastQuestion] = useState("");
  const { documents, selectedIds: selectedDocumentIds } = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState("");
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const imageInputRef = useRef(null);
  const isFullSearch = mode === "search";
  const attachmentIdsRef = useRef(new Set());
  const attachmentFilesRef = useRef(new Map());

  async function refreshDocuments() {
    setDocumentsLoading(true);
    setDocumentsError("");

    try {
      refreshDocumentStore();
    } catch (error) {
      setDocumentsError(
        error?.status === 401
          ? "سجّل الدخول لعرض المستندات المرتبطة بحسابك."
          : "تعذر مزامنة المستندات حاليًا.",
      );
    } finally {
      setDocumentsLoading(false);
    }
  }

  useEffect(() => {
    function refreshWhenVisible() {
      if (document.visibilityState === "visible") {
        void refreshDocuments();
      }
    }

    refreshWhenVisible();
    document.addEventListener("visibilitychange", refreshWhenVisible);

    function refreshAfterDocumentChange() {
      void refreshDocuments();
    }

    window.addEventListener("lexora:documents-changed", refreshAfterDocumentChange);

    return () => {
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.removeEventListener("lexora:documents-changed", refreshAfterDocumentChange);
    };
  }, []);

  async function uploadAttachment(file, source, localId) {
    attachmentFilesRef.current.set(localId, file);
    setAttachments((current) => {
      const existing = current.find((item) => item.id === localId);
      if (existing) {
        return current.map((item) => item.id === localId ? { ...item, status: "uploading", error: null } : item);
      }
      return [...current, {
        id: localId,
        name: file.name || "document",
        type: file.type || "unknown",
        size: file.size,
        sizeLabel: formatFileSize(file.size),
        source,
        file,
        status: "uploading",
        backendDocumentId: null,
        error: null,
      }];
    });

    try {
      const uploaded = await uploadDocument(file, "Contract");
      const backendDocumentId = uploaded?.id;

      if (typeof backendDocumentId !== "string" || !backendDocumentId) {
        throw new Error("تعذر تأكيد معرف المستند المرفوع.");
      }
      setDocumentsError("");
      setAttachments((current) => current.map((item) => item.id === localId ? {
        ...item,
        status: "ready",
        backendDocumentId,
        name: uploaded.fileName || item.name,
        size: uploaded.sizeBytes ?? item.size,
        sizeLabel: formatFileSize(uploaded.sizeBytes ?? item.size),
        error: null,
      } : item));
      upsertDocument({ ...uploaded, file });
      setSelectedIds([...selectedDocumentIds, backendDocumentId]);
      window.dispatchEvent(new CustomEvent("lexora:documents-changed"));
    } catch (error) {
      setAttachments((current) => current.map((item) => item.id === localId ? {
        ...item,
        status: "error",
        error: error?.message || "تعذر رفع المستند وفهرسته.",
      } : item));
    }
  }

  async function addAttachments(fileList, source) {
    const selectedFiles = Array.from(fileList || []);
    if (!selectedFiles.length) return;

    setAttachmentMenuOpen(false);

    for (const file of selectedFiles) {
      const localId = `${source}_${file.name}_${file.lastModified}_${file.size}`;
      if (attachmentIdsRef.current.has(localId)) continue;
      attachmentIdsRef.current.add(localId);
      await uploadAttachment(file, source, localId);
    }
  }

  function retryAttachment(attachment) {
    const file = attachmentFilesRef.current.get(attachment.id);
    if (attachment.status === "uploading" || !file) return;
    void uploadAttachment(file, attachment.source, attachment.id);
  }

  function removeAttachment(id) {
    const attachment = attachments.find(
      (item) => item.id === id,
    );

    attachmentIdsRef.current.delete(id);
    attachmentFilesRef.current.delete(id);

    if (
      typeof attachment?.backendDocumentId === "string"
    ) {
      setSelectedIds(
        selectedDocumentIds.filter(
          (documentId) => documentId !== attachment.backendDocumentId,
        ),
      );
    }

    setAttachments((current) =>
      current.filter((item) => item.id !== id),
    );
  }

  function getAttachmentSummary() {
    return attachments.map(({ name, type, size, source }) => ({
      name,
      type,
      size,
      source,
    }));
  }

  async function submitQuestion(trimmedQuestion) {
    if (loading) return;

    if (!trimmedQuestion) {
      setResult({
        status: "error",
        error: new Error("اكتب السؤال القانوني الاول."),
      });
      return;
    }

    if (
      attachments.some(
        (item) => item.status === "uploading",
      )
    ) {
      setResult({
        status: "error",
        error: new Error(
          "انتظر حتى تكتمل فهرسة المستندات.",
        ),
      });
      return;
    }

    const documentIds = [
      ...new Set(
        selectedDocumentIds.filter(
          (documentId) => typeof documentId === "string" && documentId,
        ),
      ),
    ];

    if (!documentIds.length) {
      setResult({
        status: "error",
        error: new Error(
          "ارفع مستندا واحدا على الأقل قبل إرسال السؤال.",
        ),
      });
      return;
    }

    setLastQuestion(trimmedQuestion);

    const attachmentSummary = getAttachmentSummary();

    setLoading(true);

    setResult({
      status: "sending",
      question: trimmedQuestion,
    });

    try {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
      setResult((current) => ({
        ...current,
        status: "retrieving",
      }));

      const response = await askDocuments(
        trimmedQuestion,
        documentIds,
      );

      setResult((current) => ({
        ...current,
        status: "generating",
      }));

      await new Promise((resolve) => window.setTimeout(resolve, 0));
      setResult({
        status: "success",
        question: trimmedQuestion,
        ...response,
        attachments: attachmentSummary,
      });
    } catch (error) {
      setResult({
        status: "error",
        question: trimmedQuestion,
        error,
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    await submitQuestion(question.trim());
  }

  async function retry() {
    if (!lastQuestion) return;
    await submitQuestion(lastQuestion);
  }

  function startNewQuestion() {
    setQuestion("");
    setLastQuestion("");
    setResult({ status: "waiting" });
  }

  async function copyAnswer() {
    if (!result.answer || !navigator.clipboard) return;

    try {
      await navigator.clipboard.writeText(result.answer);
    } catch {
      // Clipboard permissions are controlled by the browser.
    }
  }

  const confidence = typeof result.confidence === "number"
    ? Math.round(result.confidence * 100)
    : null;
  const isLowConfidence = confidence !== null && confidence < 60;
  const statusMessage = {
    sending: "جاري إرسال السؤال...",
    retrieving: "جاري البحث في المستندات المحددة...",
    generating: "جاري صياغة الإجابة...",
  }[result.status];

  return (
    <div className="react-widget legal-agent-widget">
      <div className="table-header">
        <div>
          <p className="eyebrow">AI Agent Workspace</p>
          <h2>{isFullSearch ? "البحث القانوني بالمصادر" : "اسأل المساعد القانوني"}</h2>
          <p>
           ارفع مستندا ثم اكتب سؤالك بالعربية أو الإنجليزية.
           يتم رفع المستند وفهرسته أولا، ثم تُولّد الإجابة من
           المستندات المختارة مع عرض المراجع المرتبطة بها.
          </p>
        </div>
      </div>

      <form className="assistant-form" onSubmit={handleSubmit} aria-busy={loading}>
        <label className="assistant-composer-label">
          السؤال
          <div className="assistant-composer">
            <div className="attachment-menu-wrap">
              <button
                className="attach-button"
                type="button"
                aria-label="إضافة ملف أو صورة"
                aria-expanded={attachmentMenuOpen}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setAttachmentMenuOpen((open) => !open);
                }}
              >
                +
              </button>

              {attachmentMenuOpen ? (
                <div className="attachment-menu">
                  <button type="button" aria-label="فتح الكاميرا" title="فتح الكاميرا" onClick={() => cameraInputRef.current?.click()}>
                    <img src="/assets/icons/camera.png" alt="" aria-hidden="true" />
                    الكاميرا
                  </button>
                  <button type="button" aria-label="اختيار صورة" title="اختيار صورة" onClick={() => imageInputRef.current?.click()}>
                    <img src="/assets/icons/image.png" alt="" aria-hidden="true" />
                    صورة
                  </button>
                  <button type="button" aria-label="اختيار ملف" title="اختيار ملف" onClick={() => fileInputRef.current?.click()}>
                    <img src="/assets/icons/file.png" alt="" aria-hidden="true" />
                    ملف
                  </button>
                </div>
              ) : null}
            </div>

            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="اكتب سؤالك القانوني هنا..."
              required
            />
          </div>
        </label>

        <div
          className="search-filters"
          aria-label="اختيار المستندات"
        >
          <label>
            المستندات المستخدمة في الإجابة

            <select
              multiple
              size={Math.min(
                Math.max(documents.length, 3),
                6,
              )}
              value={selectedDocumentIds.map(String)}
              disabled={
                documentsLoading ||
                documents.length === 0
              }
              onChange={(event) => {
                const ids = Array.from(
                  event.currentTarget.selectedOptions,
                  (option) => option.value,
                ).filter(Boolean);

                setSelectedIds(ids);
              }}
            >
              {documents.length ? (
                documents.map((document) => (
                  <option
                    key={document.id}
                    value={document.id}
                  >
                    {document.fileName}
                  </option>
                ))
              ) : (
                <option disabled value="">
                  لا توجد مستندات محملة
                </option>
              )}
            </select>
          </label>

          <small className="empty-result document-sync-status" role="status">
            {documentsError
              ? documentsError
              : documentsLoading
                ? "جاري مزامنة المستندات..."
                : documents.length === 0
                  ? "لا توجد مستندات متاحة حاليًا."
                  : `${selectedDocumentIds.length} من ${documents.length} مستند محدد`}
          </small>
        </div>

        <input
          ref={fileInputRef}
          className="visually-hidden"
          type="file"
          aria-hidden="true"
          tabIndex="-1"
          multiple
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
          onChange={async (event) => {
            const files = Array.from(
              event.target.files || [],
            );
            event.target.value = "";
            await addAttachments(files, "local_file");
          }}
        />
        <input
          ref={imageInputRef}
          className="visually-hidden"
          type="file"
          aria-hidden="true"
          tabIndex="-1"
          multiple
          accept=".png,.jpg,.jpeg,image/png,image/jpeg"
          onChange={async (event) => {
            const files = Array.from(
              event.target.files || [],
            );
            event.target.value = "";
            await addAttachments(files, "image");
          }}
        />
        <input
          ref={cameraInputRef}
          className="visually-hidden"
          type="file"
          aria-hidden="true"
          tabIndex="-1"
          accept="image/jpeg,image/png"
          capture="environment"
          onChange={async (event) => {
            const files = Array.from(
              event.target.files || [],
            );
            event.target.value = "";
            await addAttachments(files, "camera");
          }}
        />

        {attachments.length ? (
          <div className="attachment-list" aria-label="المرفقات المختارة">
            {attachments.map((item) => (
              <span className="attachment-chip" key={item.id}>
                <span>
                  {item.name}
                  <small>
                    {item.status === "uploading"
                      ? `جاري الرفع والفهرسة - ${item.sizeLabel}`
                      : item.status === "error"
                        ? item.error
                        : `${
                            item.source === "camera"
                              ? "كاميرا"
                              : item.source === "image"
                                ? "صورة"
                                : "ملف"
                          } - جاهز للبحث - ${item.sizeLabel}`}
                  </small>
                </span>
                {item.status === "error" ? <button data-attachment-retry type="button" aria-label={`إعادة رفع ${item.name}`} onClick={() => retryAttachment(item)}>إعادة المحاولة</button> : null}
                <button
                  type="button"
                  aria-label={`حذف ${item.name}`}
                  disabled={item.status === "uploading"}
                  onClick={() => removeAttachment(item.id)}
                >
                  x
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <button
          className="submit-btn"
          type="submit"
          disabled={
            loading ||
            attachments.some(
              (item) => item.status === "uploading",
            )
          }
        >
          {isFullSearch ? "تشغيل البحث بالمصادر" : "إرسال السؤال"}
        </button>
      </form>

      {statusMessage ? (
        <div className="rag-progress" role="status" aria-live="polite">
          <span className="status-dot" />
          <strong>{statusMessage}</strong>
          <small>هذه حالة واجهة أثناء انتظار الرد وليست نسبة تقدم من الخادم.</small>
        </div>
      ) : null}

      {result.status === "success" && !result.answer ? (
        <div className="rag-empty-state" role="status">
          <strong>لم تصل إجابة قابلة للعرض.</strong>
          <span>جرّب صياغة السؤال بطريقة مختلفة أو اختر مستندًا آخر.</span>
          <button className="ghost-btn" type="button" onClick={startNewQuestion}>سؤال جديد</button>
        </div>
      ) : null}

      {result.answer ? (
        <article className="answer-card">
          <div className="answer-heading">
            <strong>الإجابة</strong>
            <span className="answer-state">تم تجهيز الرد</span>
          </div>
          {result.question ? <p className="answer-question">السؤال: {result.question}</p> : null}
          <p>{result.answer}</p>
          {result.query_id ? <small className="answer-query-id">رقم الاستعلام: {result.query_id}</small> : null}
          {confidence !== null ? (
            <div className={`confidence-indicator${isLowConfidence ? " low" : ""}`}>
              <span>درجة الثقة</span>
              <strong>{confidence}%</strong>
              <span className="confidence-bar"><span style={{ width: `${confidence}%` }} /></span>
            </div>
          ) : null}
          {isLowConfidence ? (
            <div className="low-confidence-warning" role="status">
              الثقة منخفضة نسبيًا. راجع المصادر والنص القانوني قبل الاعتماد على الإجابة.
            </div>
          ) : null}
          <CitationList citations={result.citations || []} />
          <div className="answer-actions">
            <button className="ghost-btn" type="button" onClick={() => void copyAnswer()} disabled={!navigator.clipboard}>نسخ الإجابة</button>
            <button className="ghost-btn" type="button" onClick={startNewQuestion}>سؤال جديد</button>
          </div>
        </article>
      ) : null}

      {result.status === "error" ? <ErrorState error={result.error} onRetry={retry} /> : null}
      {result.status === "waiting" ? <p className="empty-result" role="status">في انتظار سؤالك القانوني.</p> : null}
    </div>
  );
}
