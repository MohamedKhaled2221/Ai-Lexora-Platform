import { useEffect, useRef, useState } from "react";
import { generateContract as generateContractRequest, reviewContract as reviewContractRequest } from "./apiClient.js";

const contractCatalog = [
  {
    id: "employment",
    label: "Employment Contract",
    templates: [
      {
        id: "standard-employment",
        label: "Standard Employment",
        fields: [
          ["employerName", "Employer Name", true],
          ["employeeName", "Employee Name", true],
          ["jobTitle", "Job Title", true],
          ["salary", "Salary", true],
          ["startDate", "Start Date", true],
          ["duration", "Contract Duration", true],
          ["workingHours", "Working Hours", true],
          ["benefits", "Benefits", false],
          ["termination", "Termination Conditions", true],
          ["governingLaw", "Applicable Law", true],
          ["additionalTerms", "Additional Terms", false],
        ],
      },
      {
        id: "executive-employment",
        label: "Executive Employment",
        fields: [
          ["employerName", "Employer Name", true],
          ["employeeName", "Executive Name", true],
          ["jobTitle", "Executive Title", true],
          ["salary", "Annual Compensation", true],
          ["startDate", "Start Date", true],
          ["duration", "Contract Duration", true],
          ["authority", "Authority and Reporting Line", true],
          ["benefits", "Benefits and Incentives", false],
          ["termination", "Termination Conditions", true],
          ["governingLaw", "Applicable Law", true],
        ],
      },
      {
        id: "part-time-employment",
        label: "Part-Time Employment",
        fields: [
          ["employerName", "Employer Name", true],
          ["employeeName", "Employee Name", true],
          ["jobTitle", "Job Title", true],
          ["salary", "Hourly Rate", true],
          ["startDate", "Start Date", true],
          ["workingHours", "Working Hours", true],
          ["termination", "Termination Conditions", true],
          ["governingLaw", "Applicable Law", true],
        ],
      },
    ],
  },
  {
    id: "rental",
    label: "Rental / Lease Agreement",
    templates: [
      {
        id: "residential-lease",
        label: "Residential Lease",
        fields: [["landlord", "Landlord Name", true], ["tenant", "Tenant Name", true], ["property", "Property Address", true], ["rent", "Rent", true], ["term", "Lease Term", true], ["deposit", "Security Deposit", true], ["governingLaw", "Applicable Law", true], ["additionalTerms", "Additional Terms", false]],
      },
      {
        id: "commercial-lease",
        label: "Commercial Lease",
        fields: [["landlord", "Landlord Name", true], ["tenant", "Tenant / Company Name", true], ["property", "Commercial Property Address", true], ["business", "Permitted Business Activity", true], ["rent", "Rent and Payment Schedule", true], ["term", "Lease Term", true], ["maintenance", "Maintenance Responsibilities", true], ["governingLaw", "Applicable Law", true]],
      },
    ],
  },
  {
    id: "sales",
    label: "Sales Contract",
    templates: [{ id: "standard-sales", label: "Standard Sales Contract", fields: [["seller", "Seller Name", true], ["buyer", "Buyer Name", true], ["goods", "Goods / Services", true], ["price", "Purchase Price", true], ["delivery", "Delivery Terms", true], ["payment", "Payment Terms", true], ["governingLaw", "Applicable Law", true], ["additionalTerms", "Additional Terms", false]] }],
  },
  {
    id: "partnership",
    label: "Partnership Agreement",
    templates: [{ id: "standard-partnership", label: "Standard Partnership", fields: [["partners", "Partners", true], ["business", "Business Purpose", true], ["contributions", "Capital Contributions", true], ["profitSharing", "Profit Sharing", true], ["management", "Management and Authority", true], ["exit", "Exit Conditions", true], ["governingLaw", "Applicable Law", true]] }],
  },
  {
    id: "service",
    label: "Service Agreement",
    templates: [{ id: "standard-service", label: "Standard Service Agreement", fields: [["provider", "Service Provider", true], ["client", "Client", true], ["services", "Scope of Services", true], ["fees", "Fees", true], ["term", "Service Term", true], ["confidentiality", "Confidentiality Requirements", false], ["governingLaw", "Applicable Law", true]] }],
  },
  {
    id: "nda",
    label: "Non-Disclosure Agreement (NDA)",
    templates: [{ id: "mutual-nda", label: "Mutual NDA", fields: [["parties", "Parties", true], ["purpose", "Permitted Purpose", true], ["confidentialInfo", "Confidential Information", true], ["duration", "Confidentiality Period", true], ["exceptions", "Exceptions", true], ["governingLaw", "Applicable Law", true]] }],
  },
  {
    id: "loan",
    label: "Loan Agreement",
    templates: [{ id: "standard-loan", label: "Standard Loan", fields: [["lender", "Lender", true], ["borrower", "Borrower", true], ["amount", "Loan Amount", true], ["interest", "Interest Rate", true], ["repayment", "Repayment Terms", true], ["security", "Security / Collateral", false], ["governingLaw", "Applicable Law", true]] }],
  },
  {
    id: "settlement",
    label: "Settlement Agreement",
    templates: [{ id: "standard-settlement", label: "Standard Settlement", fields: [["parties", "Parties", true], ["dispute", "Dispute Description", true], ["consideration", "Settlement Consideration", true], ["release", "Release Terms", true], ["confidentiality", "Confidentiality", false], ["governingLaw", "Applicable Law", true]] }],
  },
  {
    id: "purchase",
    label: "Purchase Agreement",
    templates: [{ id: "standard-purchase", label: "Standard Purchase", fields: [["seller", "Seller", true], ["buyer", "Buyer", true], ["asset", "Asset / Property", true], ["price", "Purchase Price", true], ["closing", "Closing Date and Conditions", true], ["representations", "Representations and Warranties", true], ["governingLaw", "Applicable Law", true]] }],
  },
  {
    id: "other",
    label: "Other",
    templates: [{ id: "custom-contract", label: "Custom Legal Contract", fields: [["parties", "Parties", true], ["purpose", "Contract Purpose", true], ["terms", "Main Terms", true], ["governingLaw", "Applicable Law", true], ["additionalTerms", "Additional Terms", false]] }],
  },
];

const statuses = ["مسودة", "تم الإنشاء بالذكاء الاصطناعي", "قيد المراجعة", "تمت المراجعة", "نهائي"];
const storageKey = "lexora-contract-draft";
const draftLanguages = [
  ["ar", "العربية"],
  ["en", "English"],
  ["mixed", "عربي / English"],
];

function getTemplateFields(template) {
  return template.fields.some(([fieldId]) => fieldId === "additionalTerms")
    ? template.fields
    : [...template.fields, ["additionalTerms", "شروط إضافية", false]];
}
const legacyStatusMap = {
  Draft: "مسودة",
  "AI Generated": "تم الإنشاء بالذكاء الاصطناعي",
  "Under Review": "قيد المراجعة",
  Reviewed: "تمت المراجعة",
  Final: "نهائي",
};

function getStoredDraft() {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey) || "null");
  } catch {
    return null;
  }
}

function normalizeStatus(status) {
  const normalizedStatus = legacyStatusMap[status] || status;
  return statuses.includes(normalizedStatus) ? normalizedStatus : "مسودة";
}

function userMessage(error) {
  if (error?.status === 503) return "خدمة الذكاء الاصطناعي غير متاحة حاليًا. حاول مرة أخرى بعد قليل.";
  if (error?.status === 401) return "سجّل الدخول أولًا لاستخدام ميزة إنشاء العقود.";
  return "تعذر إكمال الطلب. راجع البيانات وحاول مرة أخرى.";
}

function formatSavedTime(value) {
  if (!value) return "لم يتم الحفظ يدويًا بعد";
  return `آخر حفظ محلي: ${new Date(value).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" })}`;
}

function getContractSections(text) {
  return text.split("\n").map((line, index) => ({ line: line.trim(), index }))
    .filter(({ line }) => line && line.length <= 90 && !/[.!?؛،:]$/.test(line))
    .slice(0, 20);
}

function FieldEditor({ field, value, onChange }) {
  const [id, label, required] = field;
  const isLong = ["additionalTerms", "terms", "services", "dispute", "representations"].includes(id);
  return (
    <label className={`contract-field${isLong ? " contract-field-wide" : ""}`} htmlFor={`contract-${id}`}>
      {label}{required ? " *" : ""}
      {isLong ? <textarea id={`contract-${id}`} value={value || ""} onChange={(event) => onChange(id, event.target.value)} rows={3} /> : <input id={`contract-${id}`} value={value || ""} onChange={(event) => onChange(id, event.target.value)} required={required} />}
    </label>
  );
}

function ContractEditor({ value, onChange, editorRef, direction }) {
  return (
    <div className="contract-paper-wrap">
      <textarea ref={editorRef} className="contract-editor" dir={direction} aria-label="Editable generated contract" value={value} onChange={(event) => onChange(event.target.value)} placeholder="Your generated contract will appear here." />
    </div>
  );
}

export function ContractGenerationPage() {
  const storedDraft = getStoredDraft();
  const [contractType, setContractType] = useState(storedDraft?.contractType || "employment");
  const [templateId, setTemplateId] = useState(storedDraft?.templateId || "standard-employment");
  const [contractData, setContractData] = useState(storedDraft?.contractData || {});
  const [instructions, setInstructions] = useState(storedDraft?.instructions || "");
  const [contractText, setContractText] = useState(storedDraft?.contractText || "");
  const [status, setStatus] = useState(normalizeStatus(storedDraft?.status));
  const [loading, setLoading] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [error, setError] = useState("");
  const [suggestion, setSuggestion] = useState("");
  const [reviewNotes, setReviewNotes] = useState(storedDraft?.reviewNotes || "");
  const [contractName, setContractName] = useState(storedDraft?.contractName || "");
  const [contractNumber, setContractNumber] = useState(storedDraft?.contractNumber || "");
  const [clientName, setClientName] = useState(storedDraft?.clientName || "");
  const [relatedCase, setRelatedCase] = useState(storedDraft?.relatedCase || "");
  const [language, setLanguage] = useState(storedDraft?.language || "ar");
  const [jurisdiction, setJurisdiction] = useState(storedDraft?.jurisdiction || "Egypt");
  const [createdAt] = useState(storedDraft?.createdAt || new Date().toISOString());
  const [draftState, setDraftState] = useState("saved");
  const [lastSavedAt, setLastSavedAt] = useState(storedDraft?.lastSavedAt || null);
  const [reviewState, setReviewState] = useState(storedDraft?.reviewState || "idle");
  const [approvalOpen, setApprovalOpen] = useState(false);
  const approvalCancelRef = useRef(null);
  const approvalTriggerRef = useRef(null);
  const editorRef = useRef(null);

  const selectedType = contractCatalog.find((item) => item.id === contractType) || contractCatalog[0];
  const rawTemplate = selectedType.templates.find((item) => item.id === templateId) || selectedType.templates[0];
  const selectedTemplate = { ...rawTemplate, fields: getTemplateFields(rawTemplate) };

  useEffect(() => {
    if (!selectedType.templates.some((item) => item.id === templateId)) {
      setTemplateId(selectedType.templates[0].id);
      setContractData({});
    }
  }, [selectedType, templateId]);

  const draftPayload = {
    contractType,
    templateId: selectedTemplate.id,
    contractData,
    instructions,
    contractText,
    status,
    reviewNotes,
    contractName,
    contractNumber,
    clientName,
    relatedCase,
    language,
    jurisdiction,
    createdAt,
    lastSavedAt,
    reviewState,
  };

  useEffect(() => {
    setDraftState("unsaved");
    const timeoutId = window.setTimeout(() => {
      const savedAt = new Date().toISOString();
      sessionStorage.setItem(storageKey, JSON.stringify({ ...draftPayload, lastSavedAt: savedAt }));
      setLastSavedAt(savedAt);
      setDraftState("saved");
    }, 700);

    return () => window.clearTimeout(timeoutId);
  }, [contractType, selectedTemplate.id, contractData, instructions, contractText, status, reviewNotes, contractName, contractNumber, clientName, relatedCase, language, jurisdiction, createdAt, reviewState]);

  useEffect(() => {
    function warnBeforeUnload(event) {
      if (draftState !== "unsaved") return;
      event.preventDefault();
      event.returnValue = "";
    }

    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [draftState]);

  function updateField(fieldId, value) {
    setContractData((current) => ({ ...current, [fieldId]: value }));
    setError("");
  }

  function updateMetadata(setter, value) {
    setter(value);
    setError("");
  }

  function buildGenerationRequest() {
    return { contractType: selectedType.label, template: selectedTemplate.label, contractData, additionalInstructions: instructions };
  }

  function changeStatus(nextStatus) {
    if (nextStatus === "نهائي" && status !== "تمت المراجعة" && status !== "نهائي") {
      setError("لا يمكن اعتماد العقد نهائيًا قبل إتمام مراجعة المحامي.");
      return;
    }
    setStatus(nextStatus);
    setError("");
  }

  async function generateContract(event) {
    event.preventDefault();
    const missing = selectedTemplate.fields.filter(([fieldId, , required]) => required && !String(contractData[fieldId] || "").trim());
    if (missing.length) {
      setError(`أكمل الحقول المطلوبة: ${missing.map(([, label]) => label).join("، ")}.`);
      return;
    }
    setLoading(true);
    setError("");
    setSuggestion("");
    try {
      const response = await generateContractRequest(buildGenerationRequest());
      const generated = response.answer || response.message || "";
      if (!generated) throw new Error("empty-response");
      setContractText(generated);
      setStatus("تم الإنشاء بالذكاء الاصطناعي");
      setReviewState("idle");
    } catch (requestError) {
      setError(userMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  async function reviewContract(action) {
    if (!contractText.trim()) {
      setError("أنشئ عقدًا أو أدخل نص العقد قبل طلب المراجعة.");
      return;
    }
    setReviewLoading(true);
    setError("");
    setReviewState("reviewing");
    try {
      const response = await reviewContractRequest(contractText, action);
      const reviewResult = response.answer || response.message || "";
      setSuggestion(reviewResult);
      setStatus("قيد المراجعة");
      setReviewState(reviewResult ? "suggestion-available" : "no-suggestions");
    } catch (requestError) {
      setError(userMessage(requestError));
      setReviewState("error");
    } finally {
      setReviewLoading(false);
    }
  }

  function clearDraft() {
    if ((contractText || Object.keys(contractData).length || instructions || contractName || reviewNotes) && !window.confirm("هل تريد مسح المسودة المحلية الحالية؟")) return;
    setContractData({});
    setInstructions("");
    setContractText("");
    setSuggestion("");
    setReviewNotes("");
    setContractName("");
    setContractNumber("");
    setClientName("");
    setRelatedCase("");
    setLanguage("ar");
    setJurisdiction("Egypt");
    setStatus("مسودة");
    setReviewState("idle");
    setError("");
  }

  function saveDraftManually() {
    const savedAt = new Date().toISOString();
    sessionStorage.setItem(storageKey, JSON.stringify({ ...draftPayload, lastSavedAt: savedAt }));
    setLastSavedAt(savedAt);
    setDraftState("saved");
  }

  async function copyContract() {
    if (!contractText || !navigator.clipboard) return;
    await navigator.clipboard.writeText(contractText);
  }

  function printContract() {
    if (!contractText) return;
    const printWindow = window.open("", "_blank", "noopener,noreferrer");
    if (!printWindow) return;
    printWindow.document.body.textContent = contractText;
    printWindow.document.body.style.whiteSpace = "pre-wrap";
    printWindow.document.body.style.direction = language === "en" ? "ltr" : "rtl";
    printWindow.document.body.style.fontFamily = "Georgia, Times New Roman, serif";
    printWindow.print();
  }

  function downloadContract() {
    if (!contractText) return;
    const blob = new Blob([contractText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${contractName || "lexora-contract"}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function approveContract() {
    setStatus("نهائي");
    setApprovalOpen(false);
    approvalTriggerRef.current?.focus();
    setError("");
  }

  const editorDirection = language === "en" ? "ltr" : "rtl";
  const draftStateLabels = {
    unsaved: "تغييرات غير محفوظة",
    saved: "محفوظ محليًا",
  };

  useEffect(() => {
    if (!approvalOpen) return undefined;
    approvalCancelRef.current?.focus();

    function closeApprovalOnEscape(event) {
      if (event.key === "Escape") {
        setApprovalOpen(false);
        approvalTriggerRef.current?.focus();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        document.querySelectorAll(".contract-approval-modal button:not([disabled])"),
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

    document.addEventListener("keydown", closeApprovalOnEscape);
    return () => document.removeEventListener("keydown", closeApprovalOnEscape);
  }, [approvalOpen]);

  return (
    <main className="contract-page">
      <section className="page-title contract-heading">
        <div><p className="eyebrow">استوديو العقود الذكي</p><h1>إنشاء ومراجعة العقود</h1><p>أنشئ مسودة أولية بمساعدة الذكاء الاصطناعي، ثم احتفظ بالتحكم الكامل في كل قرار قانوني.</p></div>
        <div className="contract-heading-meta">
          <span className={`contract-status status-${status.toLowerCase().replace(" ", "-")}`}><span className="status-dot" />{status}</span>
          <span className={`draft-state draft-${draftState}`} role="status"><span className="status-dot" />{draftStateLabels[draftState]}</span>
        </div>
      </section>
      <div className="contract-workspace">
        <form className="contract-panel contract-form-panel" onSubmit={generateContract}>
          <div className="panel-heading"><div><p className="eyebrow">01 / الإعداد</p><h2>بيانات العقد</h2></div></div>
          <label>نوع العقد<select value={contractType} onChange={(event) => { setContractType(event.target.value); setContractData({}); setError(""); }}>{contractCatalog.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          <label>قالب العقد<select value={selectedTemplate.id} onChange={(event) => { setTemplateId(event.target.value); setContractData({}); setError(""); }}>{selectedType.templates.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          <div className="contract-metadata">
            <h3>بيانات التعريف</h3>
            <label>اسم العقد<input value={contractName} onChange={(event) => updateMetadata(setContractName, event.target.value)} placeholder="مثال: عقد عمل أحمد سالم" /></label>
            <label>رقم العقد<input value={contractNumber} onChange={(event) => updateMetadata(setContractNumber, event.target.value)} placeholder="CON-2026-001" /></label>
            <label>العميل<input value={clientName} onChange={(event) => updateMetadata(setClientName, event.target.value)} placeholder="اسم العميل أو الشركة" /></label>
            <label>القضية المرتبطة<input value={relatedCase} onChange={(event) => updateMetadata(setRelatedCase, event.target.value)} placeholder="LEX-1024 (محلي فقط)" /></label>
            <label>لغة العقد<select value={language} onChange={(event) => setLanguage(event.target.value)}>{draftLanguages.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>الاختصاص القضائي<input value={jurisdiction} onChange={(event) => updateMetadata(setJurisdiction, event.target.value)} /></label>
            <small>هذه البيانات محفوظة محليًا داخل المسودة فقط.</small>
          </div>
          <div className="contract-fields"><h3>بيانات العميل والعقد</h3>{selectedTemplate.fields.map((field) => <FieldEditor key={field[0]} field={field} value={contractData[field[0]]} onChange={updateField} />)}</div>
          <label>تعليمات إضافية<textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={4} placeholder="مثال: أضف فترة إخطار مدتها 30 يومًا وشدّد بند السرية." /></label>
          {error ? <div className="contract-alert" role="alert">{error}</div> : null}
          <button className="submit-btn" type="submit" disabled={loading}>{loading ? "جارٍ إنشاء المسودة..." : "إنشاء العقد"}</button>
          <button className="ghost-btn contract-secondary-action" type="button" onClick={clearDraft}>مسح المسودة</button>
          <p className="contract-disclaimer">الناتج مسودة تحتاج إلى مراجعة المحامي، ولا يتم اعتمادها نهائيًا تلقائيًا.</p>
        </form>

        <section className="contract-panel review-panel">
          <div className="panel-heading"><div><p className="eyebrow">02 / المراجعة</p><h2>العقد المُنشأ</h2></div><div className="status-actions">{statuses.map((item) => <button key={item} type="button" className={status === item ? "active" : ""} onClick={() => changeStatus(item)}>{item}</button>)}</div></div>
          {contractText ? <><nav className="contract-sections" aria-label="أقسام العقد"><strong>الأقسام</strong>{getContractSections(contractText).map((section) => <button key={`${section.line}-${section.index}`} type="button" onClick={() => { const position = contractText.indexOf(section.line); editorRef.current?.focus(); editorRef.current?.setSelectionRange(position, position + section.line.length); }}>{section.line}</button>)}</nav><ContractEditor direction={editorDirection} editorRef={editorRef} value={contractText} onChange={(value) => { setContractText(value); if (status === "تم الإنشاء بالذكاء الاصطناعي") setStatus("قيد المراجعة"); }} /></> : <div className="contract-empty"><h3>لا توجد مسودة بعد</h3><p>أكمل بيانات العقد وأنشئ المسودة لتظهر هنا في محرر قابل للتعديل.</p></div>}
          <div className="review-tools"><h3>مراجعة بمساعدة الذكاء الاصطناعي</h3><div className="review-actions"><button className="ghost-btn" type="button" disabled={reviewLoading} onClick={() => reviewContract("راجع هذا العقد وحدد أهم المشكلات القانونية")}>مراجعة العقد</button><button className="ghost-btn" type="button" disabled={reviewLoading} onClick={() => reviewContract("تحقق من البنود الناقصة في هذا العقد واشرح كل إضافة مقترحة")}>فحص البنود الناقصة</button><button className="ghost-btn" type="button" disabled={reviewLoading} onClick={() => reviewContract("اكتشف التناقضات في الأسماء والتواريخ والمبالغ والالتزامات والمصطلحات المعرفة")}>اكتشاف التناقضات</button></div>{reviewLoading ? <p className="empty-result" role="status">جارٍ تنفيذ المراجعة بالذكاء الاصطناعي...</p> : null}{reviewState === "no-suggestions" ? <p className="empty-result">اكتملت المراجعة ولم تُرجع اقتراحات.</p> : null}{reviewState === "error" ? <p className="contract-alert">تعذر إكمال المراجعة. لم يتم تغيير نص العقد.</p> : null}{suggestion ? <div className={`ai-suggestion suggestion-${reviewState}`}><strong>اقتراحات الذكاء الاصطناعي</strong><textarea value={suggestion} onChange={(event) => setSuggestion(event.target.value)} rows={8} /><div><button className="primary-btn" type="button" onClick={() => { setReviewNotes((current) => `${current}${current ? "\n\n" : ""}${suggestion}`); setSuggestion(""); setReviewState("accepted"); }}>حفظ كملاحظات</button><button className="ghost-btn" type="button" onClick={() => { setSuggestion(""); setReviewState("rejected"); }}>رفض</button></div><small>تبقى الاقتراحات منفصلة ولا تستبدل نص العقد.</small></div> : null}{reviewState === "accepted" ? <p className="review-state review-accepted">تم حفظ الاقتراح كملاحظة محلية.</p> : null}{reviewState === "rejected" ? <p className="review-state review-rejected">تم رفض الاقتراح محليًا.</p> : null}{reviewNotes ? <div className="review-notes"><strong>ملاحظات المحامي</strong><textarea value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} rows={6} /></div> : null}</div>
          <div className="contract-actions"><button className="ghost-btn" type="button" onClick={saveDraftManually}>حفظ محليًا</button><button className="ghost-btn" type="button" onClick={() => void copyContract()} disabled={!contractText || !navigator.clipboard}>نسخ</button><button className="ghost-btn" type="button" onClick={printContract} disabled={!contractText}>طباعة</button><button className="ghost-btn" type="button" onClick={downloadContract} disabled={!contractText}>تنزيل TXT</button><button className="primary-btn" type="button" disabled={!contractText.trim() || status !== "تمت المراجعة" || draftState === "unsaved"} onClick={(event) => { approvalTriggerRef.current = event.currentTarget; setApprovalOpen(true); }}>اعتماد محلي</button></div>
          <small className="draft-save-status" role="status">{formatSavedTime(lastSavedAt)} · لا يتم الحفظ على الخادم.</small>
        </section>
      </div>
      {approvalOpen ? <div className="contract-approval-modal" role="dialog" aria-modal="true" aria-labelledby="contract-approval-title" aria-describedby="contract-approval-description"><div className="contract-approval-box"><h2 id="contract-approval-title">اعتماد محلي للمسودة</h2><p id="contract-approval-description">سيتم تغيير الحالة داخل هذه الجلسة فقط. لا يوجد اعتماد حقيقي على الخادم حاليًا.</p><div className="contract-actions"><button ref={approvalCancelRef} className="ghost-btn" type="button" onClick={() => { setApprovalOpen(false); approvalTriggerRef.current?.focus(); }}>إلغاء</button><button className="primary-btn" type="button" onClick={approveContract}>تأكيد محلي</button></div></div></div> : null}
    </main>
  );
}
