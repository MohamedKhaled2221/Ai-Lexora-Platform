import { useMemo, useRef, useState } from "react";
import {
  API_BASE,
  buildRawRagRequest,
  requestApi,
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
    return <p className="empty-result">لم تُرجع الخدمة مراجع قابلة للعرض لهذا السؤال.</p>;
  }

  return (
    <div className="citation-list">
      {citations.map((citation) => (
        <article className="citation-card" key={`${citation.evidence_id}-${citation.document_id}-${citation.chunk_id}`}>
          <strong>{citation.evidence_id} - {citation.document_id}</strong>
          <span>المقطع: {citation.chunk_id}</span>
          {citation.page !== null && citation.page !== undefined ? <span>الصفحة: {citation.page}</span> : null}
          {citation.section ? <span>القسم: {citation.section}</span> : null}
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
  const [filters, setFilters] = useState({ document_type: "", language: "" });
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const imageInputRef = useRef(null);
  const isFullSearch = mode === "search";

  function addAttachments(fileList, source) {
    const selectedFiles = Array.from(fileList || []);

    if (!selectedFiles.length) return;

    setAttachments((current) => {
      const knownIds = new Set(current.map((item) => item.id));
      const next = selectedFiles
        .map((file) => ({
          id: `${source}_${file.name}_${file.lastModified}_${file.size}`,
          name: file.name || "camera-image",
          type: file.type || "unknown",
          size: file.size,
          sizeLabel: formatFileSize(file.size),
          source,
        }))
        .filter((item) => !knownIds.has(item.id));

      return [...current, ...next];
    });

    setAttachmentMenuOpen(false);
  }

  function removeAttachment(id) {
    setAttachments((current) => current.filter((item) => item.id !== id));
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
      setResult({ status: "error", error: new Error("اكتب السؤال القانوني الاول.") });
      return;
    }

    setLastQuestion(trimmedQuestion);
    const attachmentSummary = getAttachmentSummary();
    const endpoint = "/api/v1/rag/ask";
    const payload = buildRawRagRequest(trimmedQuestion, filters);

    setLoading(true);
    setResult({
      status: "sending",
      endpoint,
      payload,
      attachments_ready_for_future_ai_agent: attachmentSummary,
    });

    try {
      const response = await requestApi(endpoint, {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setResult({ status: "success", ...response, attachments: attachmentSummary });
    } catch (error) {
      setResult({ status: "error", error, endpoint });
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
            اكتب سؤالا بالعربية أو الإنجليزية للحصول على إجابة من مسار البحث والاسترجاع الكامل. المرفقات تُحفظ في الواجهة فقط حتى يتوفر upload endpoint.
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

        <div className="search-filters" aria-label="فلاتر البحث">
          <label>نوع المستند
            <select value={filters.document_type} onChange={(event) => setFilters({ ...filters, document_type: event.target.value })}>
              <option value="">كل الأنواع</option>
              <option value="contract">عقد</option>
              <option value="law">قانون</option>
              <option value="decree">مرسوم</option>
              <option value="court_verdict">حكم قضائي</option>
            </select>
          </label>
          <label>لغة المصدر
            <select value={filters.language} onChange={(event) => setFilters({ ...filters, language: event.target.value })}>
              <option value="">كل اللغات</option>
              <option value="ar">العربية</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>

        <input
          ref={fileInputRef}
          className="visually-hidden"
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.webp,image/*"
          onChange={(event) => {
            addAttachments(event.target.files, "local_file");
            event.target.value = "";
          }}
        />
        <input
          ref={imageInputRef}
          className="visually-hidden"
          type="file"
          multiple
          accept="image/*,.png,.jpg,.jpeg,.webp"
          onChange={(event) => {
            addAttachments(event.target.files, "image");
            event.target.value = "";
          }}
        />
        <input
          ref={cameraInputRef}
          className="visually-hidden"
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(event) => {
            addAttachments(event.target.files, "camera");
            event.target.value = "";
          }}
        />

        {attachments.length ? (
          <div className="attachment-list" aria-label="المرفقات المختارة">
            {attachments.map((item) => (
              <span className="attachment-chip" key={item.id}>
                <span>
                  {item.name}
                  <small>{item.source === "camera" ? "كاميرا" : item.source === "image" ? "صورة" : "ملف"} - {item.sizeLabel}</small>
                </span>
                <button type="button" aria-label={`حذف ${item.name}`} onClick={() => removeAttachment(item.id)}>
                  x
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <button className="submit-btn" type="submit" disabled={loading}>
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
