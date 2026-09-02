import { useMemo, useRef, useState } from "react";
import {
  API_BASE,
  askDocuments,
  listDocuments,
  requestApi,
  uploadDocument,
} from "./apiClient.js";

const cases = [
  {
    id: "LEX-1024",
    title: "نزاع عقد توريد",
    client: "شركة النور",
    lawyer: "محامي 1",
    status: "نشطة",
    priority: "متوسطة",
    deadline: "24 أغسطس",
  },
  {
    id: "LEX-1025",
    title: "استئناف حكم عمالي",
    client: "أحمد سالم",
    lawyer: "محامي 1",
    status: "عاجلة",
    priority: "عاجلة",
    deadline: "25 أغسطس",
  },
  {
    id: "LEX-1026",
    title: "قسمة تركة",
    client: "عائلة حسن",
    lawyer: "محامي 2",
    status: "معلقة",
    priority: "عادية",
    deadline: "28 أغسطس",
  },
  {
    id: "LEX-1027",
    title: "مراجعة اتفاقية شراكة",
    client: "بيتا للاستثمار",
    lawyer: "محامي 3",
    status: "مغلقة",
    priority: "منخفضة",
    deadline: "لا يوجد",
  },
];

function JsonBlock({ value }) {
  return <pre className="api-output">{JSON.stringify(value, null, 2)}</pre>;
}

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
      <p className="empty-result">
        لم تُرجع الخدمة مراجع قابلة للعرض لهذا السؤال.
      </p>
    );
  }

  return (
    <div className="citation-list">
      {citations.map((citation) => (
        <article
          className="citation-card"
          key={`${citation.evidenceId}-${citation.documentId}-${citation.chunkId}`}
        >
          <strong>
            {citation.evidenceId} - {citation.fileName}
          </strong>

          <span>
            المستند: #{citation.documentId}
          </span>

          <span>
            المقطع: {citation.chunkId}
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
        </article>
      ))}
    </div>
  );
}

export function BackendStatusWidget() {
  const [result, setResult] = useState({
    status: "waiting",
    apiBase: API_BASE,
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
        apiBase: API_BASE,
        message: error.message,
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
          <p className="eyebrow">Live Backend Widget</p>
          <h2>متابعة جاهزية خدمات النظام</h2>
          <p>مكون React يفحص FastAPI وخدمات الذكاء الاصطناعي من غير تغيير أوامر الباك.</p>
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

      <JsonBlock value={result} />
    </div>
  );
}

export function CaseInsightsWidget() {
  const [selectedLawyer, setSelectedLawyer] = useState("all");

  const filteredCases = useMemo(() => {
    if (selectedLawyer === "all") return cases;
    return cases.filter((item) => item.lawyer === selectedLawyer);
  }, [selectedLawyer]);

  const urgentCount = filteredCases.filter((item) => item.status === "عاجلة").length;
  const activeCount = filteredCases.filter((item) => item.status === "نشطة").length;
  const lawyers = ["all", "محامي 1", "محامي 2", "محامي 3"];

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

export function LegalAssistantWidget({ mode = "ai" }) {
  const [question, setQuestion] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [result, setResult] = useState({ status: "waiting" });
  const [loading, setLoading] = useState(false);
  const [lastQuestion, setLastQuestion] = useState("");
  const [documents, setDocuments] = useState([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState("");
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const imageInputRef = useRef(null);
  const isFullSearch = mode === "search";
  const attachmentIdsRef = useRef(new Set());

  async function refreshDocuments() {
    setDocumentsLoading(true);
    setDocumentsError("");

    try {
      const loaded = await listDocuments();

      const validDocuments = loaded.filter(
        (document) => Number.isInteger(document?.id),
      );

      setDocuments(validDocuments);

      const availableIds = new Set(
        validDocuments.map((document) => document.id),
      );

      setSelectedDocumentIds((current) =>
        current.filter((id) => availableIds.has(id)),
      );
    } catch (error) {
      setDocumentsError(
        error?.message ||
        "تعذر تحميل قائمة المستندات.",
      );
    } finally {
      setDocumentsLoading(false);
    }
  }
  async function addAttachments(fileList, source) {
    const selectedFiles = Array.from(fileList || []);

    if (!selectedFiles.length) return;

    setAttachmentMenuOpen(false);

    for (const file of selectedFiles) {
      const localId =
        `${source}_${file.name}_${file.lastModified}_${file.size}`;

      if (attachmentIdsRef.current.has(localId)) {
        continue;
      }

      attachmentIdsRef.current.add(localId);

      setAttachments((current) => [
        ...current,
        {
          id: localId,
          name: file.name || "document",
          type: file.type || "unknown",
          size: file.size,
          sizeLabel: formatFileSize(file.size),
          source,
          status: "uploading",
          backendDocumentId: null,
          error: null,
        },
      ]);

      try {
        const uploaded = await uploadDocument(file, "Contract");
        const backendDocumentId = Number(uploaded?.id);

        if (!Number.isInteger(backendDocumentId)) {
          throw new Error(
            "تعذر تأكيد معرف المستند المرفوع.",
          );
        }
        setDocumentsError("");
        setAttachments((current) =>
          current.map((item) =>
            item.id === localId
              ? {
                  ...item,
                  status: "ready",
                  backendDocumentId,
                  name: uploaded.fileName || item.name,
                  size: uploaded.sizeBytes ?? item.size,
                  sizeLabel: formatFileSize(
                    uploaded.sizeBytes ?? item.size,
                  ),
                  error: null,
                }
              : item,
          ),
        );
        setDocuments((current) => [
          uploaded,
          ...current.filter(
            (document) =>
              document.id !== backendDocumentId,
          ),
        ]);

        setSelectedDocumentIds((current) =>
          current.includes(backendDocumentId)
            ? current
            : [...current, backendDocumentId],
        );
      } catch (error) {
        setAttachments((current) =>
          current.map((item) =>
            item.id === localId
              ? {
                  ...item,
                  status: "error",
                  error:
                    error?.message ||
                    "تعذر رفع المستند وفهرسته.",
                }
              : item,
          ),
        );
      }
    }
  }

  function removeAttachment(id) {
    const attachment = attachments.find(
      (item) => item.id === id,
    );

    attachmentIdsRef.current.delete(id);

    if (
      Number.isInteger(
        attachment?.backendDocumentId,
      )
    ) {
      setSelectedDocumentIds((current) =>
        current.filter(
          (documentId) =>
            documentId !==
            attachment.backendDocumentId,
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
          Number.isInteger,
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
    const endpoint = "/api/search/ask";

    setLoading(true);

    setResult({
      status: "sending",
      endpoint,
    });

    try {
      const response = await askDocuments(
        trimmedQuestion,
        documentIds,
      );

      setResult({
        status: "success",
        ...response,
        attachments: attachmentSummary,
      });
    } catch (error) {
      setResult({
        status: "error",
        error,
        endpoint,
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

      <form className="assistant-form" onSubmit={handleSubmit}>
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
                  (option) => Number(option.value),
                ).filter(Number.isInteger);

                setSelectedDocumentIds(ids);
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

          <label>
            إدارة المستندات

            <button
              className="ghost-btn"
              type="button"
              disabled={
                documentsLoading ||
                attachments.some(
                  (item) =>
                    item.status === "uploading",
                )
              }
              onClick={() => void refreshDocuments()}
            >
              {documentsLoading
                ? "جاري تحميل المستندات..."
                : "تحديث قائمة المستندات"}
            </button>

            <small className="empty-result">
              {documentsError
                ? documentsError
                : documents.length === 0
                  ? "ارفع مستندا أو حدّث القائمة."
                  : `${selectedDocumentIds.length} من ${documents.length} مستند محدد`}
            </small>
          </label>
        </div>

        <input
          ref={fileInputRef}
          className="visually-hidden"
          type="file"
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

      {result.answer ? (
        <article className="answer-card">
          <strong>الإجابة</strong>
          <p>{result.answer}</p>
          <span>درجة الثقة: {Math.round((result.confidence || 0) * 100)}%</span>
          <CitationList citations={result.citations || []} />
        </article>
      ) : null}

      {result.status === "error" ? <ErrorState error={result.error} onRetry={retry} /> : null}
      {result.status === "waiting" ? <p className="empty-result">في انتظار سؤالك القانوني.</p> : null}
    </div>
  );
}
