import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  askDocuments,
  checkPackage2Health,
  checkPackage2Readiness,
  deleteDocument as deleteBackendDocument,
  downloadDocument as downloadBackendDocument,
  requestApi,
  uploadDocument,
} from "./apiClient.js";
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

const documentStatusLabels = {
  processing: "قيد المعالجة",
  processed: "جاهز للبحث",
  failed: "فشلت المعالجة",
};

const documentActionLabels = {
  preview: "معاينة محلية",
  download: "تنزيل من الخادم",
  retry: "إعادة المحاولة",
};

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
        const fileName = citation.file_name ?? citation.fileName;
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
            المستند: {fileName || `#${documentId}`}
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
          <small className="citation-unavailable">معرف المستند: #{documentId}</small>
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
      const payload = path === "/health"
        ? await checkPackage2Health()
        : await checkPackage2Readiness();
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

function useAttachmentMenu() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function closeOnOutsideClick(event) {
      if (!event.target.closest(".attachment-menu-wrap")) setOpen(false);
    }
    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("click", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("click", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  return [open, setOpen];
}

function ChatAttachmentMenu({ fileInputRef, imageInputRef, cameraInputRef, open, setOpen }) {
  return (
    <div className="attachment-menu-wrap">
      <button
        className={`attach-button${open ? " is-open" : ""}`}
        type="button"
        aria-label="إضافة ملف أو صورة"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((current) => !current);
        }}
      >+
      </button>
      {open ? (
        <div className="attachment-menu" role="menu">
          <button type="button" role="menuitem" onClick={() => { setOpen(false); cameraInputRef.current?.click(); }}><img src="/assets/icons/camera.png" alt="" />كاميرا</button>
          <button type="button" role="menuitem" onClick={() => { setOpen(false); imageInputRef.current?.click(); }}><img src="/assets/icons/image.png" alt="" />صورة</button>
          <button type="button" role="menuitem" onClick={() => { setOpen(false); fileInputRef.current?.click(); }}><img src="/assets/icons/file.png" alt="" />ملف</button>
        </div>
      ) : null}
    </div>
  );
}

function ChatBubble({ message }) {
  const userMessage = message.role === "user";
  return (
    <article className={`chat-bubble-row ${userMessage ? "user" : "assistant"}`}>
      <div className="chat-avatar">{userMessage ? "أنت" : "LX"}</div>
      <div className="chat-bubble">
        <strong>{userMessage ? "أنت" : "المساعد القانوني"}</strong>
        <p>{message.content}</p>
        {message.citations?.length ? <small>{message.citations.length} مراجع مرتبطة بالإجابة</small> : null}
      </div>
    </article>
  );
}

export function ChatbotWidget() {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [menuOpen, setMenuOpen] = useAttachmentMenu();
  const fileInputRef = useRef(null);
  const imageInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const recognitionRef = useRef(null);
  const { documents, selectedIds } = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  function addFiles(fileList, source) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setAttachments((current) => [
      ...current,
      ...files.map((file) => ({
        id: `${source}-${file.name}-${file.lastModified}-${file.size}`,
        file,
        source,
        status: "ready",
      })),
    ]);
  }

  function toggleMicrophone() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("التعرف على الصوت غير متاح في هذا المتصفح.");
      return;
    }
    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "ar-EG";
    recognition.interimResults = true;
    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => {
      setIsListening(false);
      setError("تعذر التقاط الصوت. حاول مرة أخرى.");
    };
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map((result) => result[0].transcript).join("");
      setQuestion((current) => `${current} ${transcript}`.trim());
    };
    recognitionRef.current = recognition;
    recognition.start();
  }

  async function submitMessage(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text || loading) return;
    setLoading(true);
    setError("");
    setMessages((current) => [...current, { role: "user", content: text }]);
    setQuestion("");

    try {
      for (const attachment of attachments) {
        await uploadDocument(attachment.file, "Contract");
      }
      const response = await askDocuments(text, selectedIds);
      setMessages((current) => [...current, {
        role: "assistant",
        content: response.answer || "لم تصل إجابة قابلة للعرض.",
        citations: response.citations || [],
      }]);
      setAttachments([]);
      window.dispatchEvent(new CustomEvent("lexora:documents-changed"));
    } catch (requestError) {
      setError(requestError.message || "تعذر إرسال السؤال.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chatgpt-shell">
      <header className="chat-page-header">
        <div>
          <p className="eyebrow">AI Legal Workspace</p>
          <h1>المساعد القانوني</h1>
          <span>محادثة ذكية مرتبطة بمستنداتك</span>
        </div>
        <StatusPill state="ready">جاهز للمساعدة</StatusPill>
      </header>
      <div className="chat-layout">
        <aside className="chat-sidebar">
          <button className="new-chat-button" type="button" onClick={() => { setMessages([]); setQuestion(""); setAttachments([]); setError(""); }}><span>+</span> محادثة جديدة</button>
          <div className="chat-sidebar-section"><small>المحادثة الحالية</small><div className="chat-sidebar-current">محادثة قانونية جديدة</div></div>
          <div className="chat-sidebar-note"><strong>ملاحظة</strong><span>سجل المحادثات سيُربط لاحقًا بخدمة الـ Backend.</span></div>
        </aside>
        <section className="chat-main">
          <div className="chat-messages" aria-live="polite">
            {!messages.length ? <div className="chat-welcome"><div className="chat-welcome-mark">LX</div><h2>كيف أساعدك اليوم؟</h2><p>ارفع مستندًا أو اكتب سؤالك القانوني، وسأساعدك في فهم النصوص والمراجع.</p><div className="chat-suggestions"><button type="button" onClick={() => setQuestion("ما أهم الالتزامات في هذا العقد؟")}>ما أهم الالتزامات في هذا العقد؟</button><button type="button" onClick={() => setQuestion("ما البنود التي تحتاج مراجعة؟")}>ما البنود التي تحتاج مراجعة؟</button></div></div> : messages.map((message, index) => <ChatBubble key={`${message.role}-${index}`} message={message} />)}
            {loading ? <div className="chat-typing"><span /><span /><span /> المساعد يراجع المستندات...</div> : null}
          </div>
          {error ? <div className="agent-error" role="alert"><strong>تعذر تنفيذ الطلب</strong><p>{error}</p></div> : null}
          <form className="chat-composer chatgpt-composer" onSubmit={submitMessage}>
            <div className="chat-composer-input-row">
              <ChatAttachmentMenu fileInputRef={fileInputRef} imageInputRef={imageInputRef} cameraInputRef={cameraInputRef} open={menuOpen} setOpen={setMenuOpen} />
              <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="اكتب رسالتك القانونية..." aria-label="رسالتك القانونية" rows="1" required />
              <button className={`microphone-button${isListening ? " is-listening" : ""}`} type="button" aria-label="التحدث" title="التحدث" onClick={toggleMicrophone}>◉</button>
              <button className="chat-send-button" type="submit" aria-label="إرسال" title="إرسال" disabled={loading || !question.trim()}>↑</button>
            </div>
            {attachments.length ? <div className="chat-attachment-preview">{attachments.map((item) => <span key={item.id}>{item.file.name}<button type="button" aria-label={`إزالة ${item.file.name}`} onClick={() => setAttachments((current) => current.filter((file) => file.id !== item.id))}>×</button></span>)}</div> : null}
            <div className="chat-composer-meta"><small>{documents.length ? `${documents.length} مستند متاح` : "ارفع ملفًا للبدء"}</small><small>قد تحتاج الإجابات إلى مراجعة قانونية</small></div>
            <input ref={fileInputRef} className="visually-hidden" type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.json,.png,.jpg,.jpeg" onChange={(event) => { addFiles(event.target.files, "file"); event.target.value = ""; }} />
            <input ref={imageInputRef} className="visually-hidden" type="file" multiple accept=".png,.jpg,.jpeg,image/png,image/jpeg" onChange={(event) => { addFiles(event.target.files, "image"); event.target.value = ""; }} />
            <input ref={cameraInputRef} className="visually-hidden" type="file" accept="image/jpeg,image/png" capture="environment" onChange={(event) => { addFiles(event.target.files, "camera"); event.target.value = ""; }} />
          </form>
        </section>
      </div>
    </div>
  );
}

function importanceForToken(token) {
  const normalized = token.toLowerCase();
  if (/\b(article|section|المادة|البند|القانون|عقد|contract|agreement|shall|يجب|يلتزم|يحظر|لا يجوز|تعويض|غرامة|termination|confidential)\b/i.test(normalized)) return "high";
  if (/\b(may|must|unless|within|before|after|only|يجوز|خلال|قبل|بعد|فقط|شرط|مدة|تاريخ|مبلغ)\b/i.test(normalized)) return "medium";
  return "low";
}

function HighlightedText({ text }) {
  return <div className="highlighted-document-text">{text.split(/(\s+)/).map((part, index) => part.trim() ? <mark className={`importance-${importanceForToken(part)}`} key={`${part}-${index}`}>{part}</mark> : part)}</div>;
}

export function FileAnalysisWidget() {
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  async function analyzeFile(selectedFile) {
    if (!selectedFile) return;
    setFile(selectedFile);
    setStatus("loading");
    setError("");
    setText("");
    try {
      const parser = await import("../utils/documentParser.js");
      const result = await parser.parseDocumentFile(selectedFile);
      setText(result.text || "");
      setStatus(result.text ? "success" : "empty");
    } catch (parseError) {
      setStatus("error");
      setError(parseError.message || "تعذر قراءة الملف داخل المتصفح.");
    }
  }

  return (
    <div className="file-analysis-shell">
      <header className="analysis-page-header">
        <div><p className="eyebrow">Document Intelligence</p><h1>تحليل الملفات</h1><p>حوّل المستند أو الصورة إلى نص قابل للقراءة، ثم راجع الكلمات المهمة بتدرج بصري واضح.</p></div>
        <StatusPill state={status === "success" ? "ready" : status === "error" ? "error" : "idle"}>{status === "loading" ? "جاري القراءة" : status === "success" ? "تم استخراج النص" : "جاهز للبدء"}</StatusPill>
      </header>
      <div className="analysis-upload-zone">
        <input id="analysis-file-input" className="visually-hidden" type="file" accept=".pdf,.docx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp" onChange={(event) => { void analyzeFile(event.target.files?.[0]); event.target.value = ""; }} />
        <label htmlFor="analysis-file-input" className="analysis-dropzone"><span className="analysis-upload-icon">↑</span><strong>{file ? file.name : "ارفع ملفًا للتحليل"}</strong><span>PDF، DOCX، TXT، MD، CSV، JSON والصور</span><small>تتم القراءة محليًا داخل المتصفح في هذه المرحلة</small></label>
        {file ? <button className="ghost-btn" type="button" onClick={() => { setFile(null); setText(""); setStatus("idle"); setError(""); }}>اختيار ملف آخر</button> : null}
      </div>
      <div className="analysis-legend"><span><i className="legend-dot high" />أهمية عالية</span><span><i className="legend-dot medium" />أهمية متوسطة</span><span><i className="legend-dot low" />نص عادي</span></div>
      {status === "loading" ? <div className="analysis-state">جاري استخراج النص وتحليل الكلمات...</div> : null}
      {status === "error" ? <div className="agent-error" role="alert"><strong>تعذر قراءة الملف</strong><p>{error}</p></div> : null}
      {status === "empty" ? <div className="analysis-state">تمت قراءة الملف، لكن لم يتم العثور على نص قابل للعرض.</div> : null}
      {status === "success" ? <section className="analysis-result"><div className="analysis-result-heading"><div><p className="eyebrow">Extracted Text</p><h2>النص المستخرج</h2></div><span>{text.split(/\s+/).filter(Boolean).length} كلمة</span></div><HighlightedText text={text} /></section> : null}
    </div>
  );
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
      await refreshDocumentStore();
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

  async function removeDocument(documentId) {
    await deleteBackendDocument(documentId);
    await refreshDocumentStore();
    removeStoredDocument(documentId);
  }

  async function downloadDocument(document) {
    const blob = await downloadBackendDocument(document.id);
    const url = URL.createObjectURL(blob);
    const link = window.document.createElement("a");
    link.href = url;
    link.download = document.fileName || "document";
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
      void downloadDocument(document).catch((downloadError) => {
        setError(downloadError?.message || "تعذر تنزيل المستند.");
      });
      return;
    }
    if (action === "delete") {
      void removeDocument(document.id).catch((deleteError) => {
        setError(deleteError?.message || "تعذر حذف المستند من الخادم.");
      });
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
                  disabled={document.status !== "processed"}
                />
                <span>تحديد</span>
              </label>
              <span className={`document-status status-${document.status}`}>
                {documentStatusLabel(document.status)}
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
            {document.status === "processed" ? <p className="document-detail">جاهز للبحث والتنزيل من الخادم.</p> : null}
            <div className="document-actions">
              {document.status === "failed" ? <button className="ghost-btn" type="button" onClick={() => retryDocument(document)}>{documentActionLabels.retry}</button> : null}
              {document.status === "processed" ? <>
                {document.localFileAvailable ? <button className="ghost-btn" type="button" onClick={(event) => handleDocumentAction("preview", document, event.currentTarget)}>{documentActionLabels.preview}</button> : null}
                <button className="ghost-btn" type="button" onClick={() => handleDocumentAction("download", document)}>{documentActionLabels.download}</button>
              </> : null}
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

  useEffect(() => {
    function closeAttachmentMenu(event) {
      if (!event.target.closest(".attachment-menu-wrap")) {
        setAttachmentMenuOpen(false);
      }
    }

    function closeOnEscape(event) {
      if (event.key === "Escape") setAttachmentMenuOpen(false);
    }

    document.addEventListener("click", closeAttachmentMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("click", closeAttachmentMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  async function refreshDocuments() {
    setDocumentsLoading(true);
    setDocumentsError("");

    try {
      await refreshDocumentStore();
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

      if (backendDocumentId === undefined || backendDocumentId === null || backendDocumentId === "") {
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

    if (!documents.length) {
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
            <h2>{isFullSearch ? "البحث القانوني بالمصادر" : mode === "analysis" ? "تحليل الملفات" : "اسأل المساعد القانوني"}</h2>
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
                  : `${documents.length} مستند متاح لحسابك`}
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
          {isFullSearch ? "تشغيل البحث بالمصادر" : mode === "analysis" ? "بدء تحليل الملف" : "إرسال السؤال"}
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
