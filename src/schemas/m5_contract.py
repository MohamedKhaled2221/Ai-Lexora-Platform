"""
M5 Contract Schema — Approved Clause Library & Generation Rules.

Defines the data models for the M5 clause engine, including:
- Clause metadata and approval lifecycle
- Compatibility rules between clauses
- Template-level clause requirements
- Special condition resolution
- Handoff interfaces to M1 and M4
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class ClauseType(str, Enum):
    """نوع البند القانوني."""

    TERMINATION = "termination"
    INDEMNITY = "indemnity"
    CONFIDENTIALITY = "confidentiality"
    FORCE_MAJEURE = "force_majeure"
    GOVERNING_LAW = "governing_law"
    DISPUTE_RESOLUTION = "dispute_resolution"
    LIABILITY_LIMITATION = "liability_limitation"
    PAYMENT_TERMS = "payment_terms"
    WARRANTY = "warranty"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    NON_COMPETE = "non_compete"
    DATA_PROTECTION = "data_protection"
    PENALTY = "penalty"
    NOTICE = "notice"
    ASSIGNMENT = "assignment"
    SEVERABILITY = "severability"
    ENTIRE_AGREEMENT = "entire_agreement"
    AMENDMENT = "amendment"
    CUSTOM = "custom"


class Jurisdiction(str, Enum):
    """الولايات القضائية المدعومة."""

    EG = "EG"
    KSA = "KSA"
    UAE = "UAE"
    INTERNATIONAL = "INTERNATIONAL"


class DocumentType(str, Enum):
    """أنواع المستندات القانونية المدعومة."""

    EMPLOYMENT_CONTRACT = "employment_contract"
    SERVICE_AGREEMENT = "service_agreement"
    NDA = "nda"
    LEASE_AGREEMENT = "lease_agreement"
    PARTNERSHIP_AGREEMENT = "partnership_agreement"
    SALES_CONTRACT = "sales_contract"
    CONSULTING_AGREEMENT = "consulting_agreement"
    LICENSE_AGREEMENT = "license_agreement"
    LOAN_AGREEMENT = "loan_agreement"
    DISTRIBUTION_AGREEMENT = "distribution_agreement"


class ApprovalStatus(str, Enum):
    """حالة اعتماد البند في دورة الحياة."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    LAWYER_EDITED = "lawyer_edited"


class ClauseRequirement(str, Enum):
    """مستوى إلزامية البند في template معين."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    PROHIBITED = "prohibited"
    CONDITIONAL = "conditional"


class CompatibilityRelationship(str, Enum):
    """نوع العلاقة بين بندين."""

    INCOMPATIBLE = "incompatible"
    REQUIRES = "requires"
    RECOMMENDS = "recommends"


# ──────────────────────────────────────────────
# Core Models
# ──────────────────────────────────────────────

class ClauseMetadata(BaseModel):
    """بيانات وصفية إضافية للبند."""

    model_config = ConfigDict(extra="allow")

    risk_level: str = Field(
        default="medium",
        description="مستوى المخاطرة: low, medium, high",
    )
    category: str = Field(
        default="general",
        description="تصنيف البند",
    )
    notes: str = Field(
        default="",
        description="ملاحظات إضافية",
    )
    keywords_ar: list[str] = Field(
        default_factory=list,
        description="كلمات مفتاحية بالعربي للبحث",
    )
    keywords_en: list[str] = Field(
        default_factory=list,
        description="كلمات مفتاحية بالإنجليزي للبحث",
    )
    insertion_key: Optional[str] = Field(
        default=None,
        description="مفتاح/موقع إدراج البند في النموذج (e.g. 'section_termination' or '{{TERMINATION_CLAUSE}}')",
    )


class ApprovedClause(BaseModel):
    """
    البند القانوني المعتمد — الوحدة الأساسية في مكتبة M5.

    كل بند يحمل هوية فريدة ومعلومات كاملة عن نوعه،
    الولاية القضائية، حالة الاعتماد، والنص القانوني.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    clause_id: str = Field(
        ...,
        min_length=1,
        description="معرف فريد للبند (e.g. CLZ-TERM-EG-001)",
    )
    type: ClauseType = Field(
        ...,
        description="نوع البند القانوني",
    )
    jurisdiction: Jurisdiction = Field(
        ...,
        description="الولاية القضائية التي يسري فيها البند",
    )
    document_types: list[DocumentType] = Field(
        ...,
        min_length=1,
        description="أنواع المستندات التي يصلح لها البند",
    )
    version: str = Field(
        default="1.0.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="رقم الإصدار (Semantic Versioning)",
    )
    approval_status: ApprovalStatus = Field(
        default=ApprovalStatus.DRAFT,
        description="حالة الاعتماد الحالية",
    )
    effective_date: datetime = Field(
        ...,
        description="تاريخ بداية سريان البند",
    )
    expiry_date: Optional[datetime] = Field(
        default=None,
        description="تاريخ انتهاء صلاحية البند (None = سارٍ بلا حد)",
    )
    owner: str = Field(
        ...,
        min_length=1,
        description="المسؤول عن البند",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="مصدر البند القانوني (e.g. Egyptian Labor Law Art. 69)",
    )
    text_ar: str = Field(
        ...,
        min_length=1,
        description="النص القانوني بالعربية",
    )
    text_en: str = Field(
        ...,
        min_length=1,
        description="النص القانوني بالإنجليزية",
    )
    metadata: ClauseMetadata = Field(
        default_factory=ClauseMetadata,
        description="بيانات وصفية إضافية",
    )
    superseded_by: Optional[str] = Field(
        default=None,
        description="معرف البند الذي حل محل هذا البند",
    )
    supersedes: Optional[str] = Field(
        default=None,
        description="معرف البند الذي يحل محله هذا البند",
    )
    is_lawyer_edited: bool = Field(
        default=False,
        description="هل تم تعديل البند بواسطة محامٍ",
    )
    requires_separate_approval: bool = Field(
        default=False,
        description="هل يحتاج البند إلى موافقة منفصلة لإعادة الاستخدام",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="وسوم تصنيفية للبند",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="تاريخ إنشاء البند",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="تاريخ آخر تعديل",
    )

    @field_validator("clause_id")
    @classmethod
    def validate_clause_id_format(cls, value: str) -> str:
        if not value.startswith("CLZ-"):
            raise ValueError(
                "clause_id must start with 'CLZ-' prefix"
            )
        return value

    def is_active(self) -> bool:
        """هل البند ساري وفعّال حالياً."""
        if self.approval_status != ApprovalStatus.APPROVED:
            return False
        now = datetime.now(timezone.utc)
        if self.effective_date > now:
            return False
        if self.expiry_date and self.expiry_date < now:
            return False
        return True

    def is_usable(self) -> bool:
        """هل يمكن استخدام البند (ساري ولا يحتاج إعادة اعتماد)."""
        if not self.is_active():
            return False
        if self.is_lawyer_edited and self.requires_separate_approval:
            return False
        return True


# ──────────────────────────────────────────────
# Compatibility Rules
# ──────────────────────────────────────────────

class ClauseCompatibilityRule(BaseModel):
    """قاعدة توافق/تعارض بين بندين."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(
        ...,
        min_length=1,
        description="معرف فريد للقاعدة",
    )
    clause_id_a: str = Field(
        ...,
        description="البند الأول",
    )
    clause_id_b: str = Field(
        ...,
        description="البند الثاني",
    )
    relationship: CompatibilityRelationship = Field(
        ...,
        description="نوع العلاقة بين البندين",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="سبب القاعدة",
    )


# ──────────────────────────────────────────────
# Template Clause Requirements
# ──────────────────────────────────────────────

class ConditionalClause(BaseModel):
    """بند مشروط — يُطلب فقط عند تحقق شرط معين."""

    model_config = ConfigDict(extra="forbid")

    clause_id: str = Field(
        ...,
        description="معرف البند المشروط",
    )
    condition: str = Field(
        ...,
        description="الشرط الذي يجعل البند مطلوباً",
    )
    description: str = Field(
        default="",
        description="وصف الشرط",
    )


class TemplateClauseRequirement(BaseModel):
    """متطلبات البنود لنموذج عقد محدد."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(
        ...,
        min_length=1,
        description="معرف النموذج",
    )
    document_type: DocumentType = Field(
        ...,
        description="نوع المستند",
    )
    jurisdiction: Jurisdiction = Field(
        ...,
        description="الولاية القضائية",
    )
    required_clauses: list[str] = Field(
        default_factory=list,
        description="قائمة clause_id للبنود الإلزامية",
    )
    optional_clauses: list[str] = Field(
        default_factory=list,
        description="قائمة clause_id للبنود الاختيارية",
    )
    prohibited_clauses: list[str] = Field(
        default_factory=list,
        description="قائمة clause_id للبنود الممنوعة",
    )
    conditional_clauses: list[ConditionalClause] = Field(
        default_factory=list,
        description="قائمة البنود المشروطة",
    )
    section_placeholders: dict[str, str] = Field(
        default_factory=dict,
        description="خريطة مواضع الإدراج والـ placeholders المتاحة في النموذج",
    )
    template_structure: str = Field(
        default="",
        description="الهيكل النصي المرجعي للنموذج بالـ placeholders",
    )


# ──────────────────────────────────────────────
# Special Condition Resolution
# ──────────────────────────────────────────────

class SpecialConditionResult(BaseModel):
    """نتيجة محاولة حل شرط خاص."""

    model_config = ConfigDict(extra="forbid")

    condition: str = Field(
        ...,
        description="الشرط الخاص المطلوب حله",
    )
    resolved: bool = Field(
        ...,
        description="هل تم إيجاد بند معتمد مطابق",
    )
    matched_clause: Optional[ApprovedClause] = Field(
        default=None,
        description="البند المعتمد المطابق (إن وُجد)",
    )
    requires_lawyer_input: bool = Field(
        default=False,
        description="هل يحتاج تدخل محامٍ",
    )
    reason: str = Field(
        ...,
        description="سبب النتيجة",
    )


# ──────────────────────────────────────────────
# Approval Events
# ──────────────────────────────────────────────

class ApprovalEvent(BaseModel):
    """حدث في سجل اعتماد البند."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        ...,
        description="معرف الحدث",
    )
    clause_id: str = Field(
        ...,
        description="معرف البند",
    )
    action: str = Field(
        ...,
        description="نوع الحدث (submit, approve, reject, edit, supersede)",
    )
    from_status: ApprovalStatus = Field(
        ...,
        description="الحالة السابقة",
    )
    to_status: ApprovalStatus = Field(
        ...,
        description="الحالة الجديدة",
    )
    actor: str = Field(
        ...,
        description="من قام بالحدث",
    )
    reason: str = Field(
        default="",
        description="سبب الحدث",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="توقيت الحدث",
    )


# ──────────────────────────────────────────────
# Traceability
# ──────────────────────────────────────────────

class TraceRecord(BaseModel):
    """سجل تتبع استخدام بند في مستند."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(
        ...,
        description="معرف سجل التتبع",
    )
    clause_id: str = Field(
        ...,
        description="معرف البند المستخدم",
    )
    clause_version: str = Field(
        ...,
        description="إصدار البند المستخدم",
    )
    document_id: str = Field(
        ...,
        description="معرف المستند",
    )
    section: str = Field(
        default="",
        description="القسم/الموقع داخل المستند",
    )
    used_by: str = Field(
        default="system",
        description="من استخدم البند",
    )
    used_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="وقت الاستخدام",
    )


# ──────────────────────────────────────────────
# Version Entry
# ──────────────────────────────────────────────

class VersionEntry(BaseModel):
    """سجل إصدار لبند معين."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(
        ...,
        description="رقم الإصدار",
    )
    clause_id: str = Field(
        ...,
        description="معرف البند",
    )
    changes: str = Field(
        default="",
        description="وصف التغييرات",
    )
    created_by: str = Field(
        default="system",
        description="من أنشأ الإصدار",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="وقت الإنشاء",
    )
    clause_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="لقطة كاملة للبند في هذا الإصدار",
    )


# ──────────────────────────────────────────────
# Validation Reports
# ──────────────────────────────────────────────

class CompatibilityResult(BaseModel):
    """نتيجة فحص توافق بين بندين."""

    model_config = ConfigDict(extra="forbid")

    compatible: bool = Field(
        ...,
        description="هل البندان متوافقان",
    )
    relationship: Optional[CompatibilityRelationship] = Field(
        default=None,
        description="نوع العلاقة (إن وُجدت قاعدة)",
    )
    reason: str = Field(
        default="",
        description="سبب النتيجة",
    )


class CompletenessReport(BaseModel):
    """تقرير اكتمال البنود لنموذج عقد."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(..., description="معرف النموذج")
    is_complete: bool = Field(..., description="هل كل البنود الإلزامية موجودة")
    missing_required: list[str] = Field(
        default_factory=list,
        description="بنود إلزامية مفقودة",
    )
    included_prohibited: list[str] = Field(
        default_factory=list,
        description="بنود ممنوعة موجودة",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="تحذيرات",
    )


class ValidationReport(BaseModel):
    """تقرير شامل لفحص مجموعة بنود."""

    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(..., description="هل المجموعة صالحة")
    completeness: Optional[CompletenessReport] = Field(
        default=None,
        description="تقرير الاكتمال",
    )
    incompatible_pairs: list[tuple[str, str, str]] = Field(
        default_factory=list,
        description="أزواج بنود متعارضة مع السبب",
    )
    inactive_clauses: list[str] = Field(
        default_factory=list,
        description="بنود غير سارية",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="أخطاء",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="تحذيرات",
    )


# ──────────────────────────────────────────────
# Provenance Report
# ──────────────────────────────────────────────

class ProvenanceReport(BaseModel):
    """تقرير مصدر وتتبع بنود مستند."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., description="معرف المستند")
    traces: list[TraceRecord] = Field(
        default_factory=list,
        description="سجلات التتبع",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="وقت إنشاء التقرير",
    )


# ──────────────────────────────────────────────
# Handoff Interfaces
# ──────────────────────────────────────────────

class M5ToM1Handoff(BaseModel):
    """
    M5 → M1 Handoff.

    يحتوي على البنود المعتمدة، قرارات التوافق،
    والبيانات الوصفية المصدرية.
    """

    model_config = ConfigDict(extra="forbid")

    clauses: list[ApprovedClause] = Field(
        ...,
        description="البنود المعتمدة المختارة",
    )
    compatibility_decisions: list[ClauseCompatibilityRule] = Field(
        default_factory=list,
        description="قرارات التوافق المطبقة",
    )
    template_requirement: TemplateClauseRequirement = Field(
        ...,
        description=(
            "Authoritative M5 template clause requirements "
            "for this document type and jurisdiction"
        ),
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="بيانات مصدرية",
    )


class M5ToM4Handoff(BaseModel):
    """
    M5 → M4 Handoff.

    يحتوي على قواعد التحقق من المصدر والحالة
    التي يستخدمها M4 validator.
    """

    model_config = ConfigDict(extra="forbid")

    provenance_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="قواعد التحقق من المصدر",
    )
    status_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="قواعد التحقق من الحالة",
    )
    validation_context: dict[str, Any] = Field(
        default_factory=dict,
        description="سياق التحقق",
    )
