RULES = [

    # =========================================================
    # R001 - Termination / Article 157
    # =========================================================

    {
        "rule_id": "R001",
        "clause_type": "Termination",
        "rule_type": "legal_rule",
        "trigger": "breach_without_notice",

        "risk_category": "risky_clause",
        "severity": "medium",

        "legal_reference": {
            "law": "Egyptian Civil Code",
            "article": "157",
        },

        "description": (
            "A termination clause triggered by breach without "
            "the required notice should be reviewed."
        ),

        "required_terms": [
            "breach",
            "terminate",
        ],

        "forbidden_terms": [
            "notice",
        ],

        "risk_terms": [],
    },


    # =========================================================
    # R002 - Agreed Compensation / Article 224
    # =========================================================

    {
    "rule_id": "R002",
    "rule_type": "legal_rule",
    "clause_type": "Penalty",
    "trigger": "agreed_compensation",
    "risk_category": "risky_clause",
    "severity": "medium",
    "description": (
        "An agreed compensation or penalty clause containing a specified "
        "monetary amount should be reviewed, particularly where the amount "
        "may be excessively high."
    ),

    # ---------------------------------------------------------
    # بدايه التعديل الاول
    # ---------------------------------------------------------
    # "required_terms": ["penalty"],
    # "forbidden_terms": [
    #     "no penalty",
    #     "no penalties",
    #     "without penalty",
    #     "penalty shall not apply",
    #     "penalties shall not apply",
    # ],
    # ---------------------------------------------------------
    # نص التعديل الاول 
    # ---------------------------------------------------------
        "required_terms": ["penalty", "غرامة", "شرط جزائي"],
    "forbidden_terms": [
        "no penalty",
        "no penalties",
        "without penalty",
        "penalty shall not apply",
        "penalties shall not apply",
        "بدون غرامة",
        "دون غرامة",
        "لا توجد غرامة",
    ],
    # ---------------------------------------------------------
    # نهايه نص التعديل الاول
    # ---------------------------------------------------------

    "risk_terms": [],
    "legal_reference": {
        "article": "224",
        "law": "Egyptian Civil Code",
    },
},

    # =========================================================
    # R003 - Undue Payment / Article 181
    # =========================================================

    {
        "rule_id": "R003",
        "clause_type": "Payment",
        "rule_type": "legal_rule",
        "trigger": "undue_payment",

        "risk_category": "risky_clause",
        "severity": "medium",

        "legal_reference": {
            "law": "Egyptian Civil Code",
            "article": "181",
        },

        "description": (
            "A payment described as an amount that is not legally "
            "due should be reviewed for possible restitution."
        ),

        "required_terms": [],

        "forbidden_terms": [],

        "risk_terms": [
            "not due",
            "undue",
            "not legally owed",
            "not owed",
        ],
    },


    # =========================================================
    # R004 - Modified Renewal
    # =========================================================

    {
        "rule_id": "R004",
        "clause_type": "Renewal",
        "rule_type": "engineering_rule",
        "trigger": "modified_renewal",

        "risk_category": "modified_clause",
        "severity": "medium",

        "legal_reference": None,

        "description": (
            "A modified renewal clause should be reviewed "
            "against the approved reference clause."
        ),

        "required_terms": [],
        "forbidden_terms": [],
        "risk_terms": [],

        "use_is_modified": True,
    },


    # =========================================================
    # R005 - Modified Renewal With Low Similarity
    # =========================================================

    {
        "rule_id": "R005",
        "clause_type": "Renewal",
        "rule_type": "engineering_rule",
        "trigger": "modified_renewal_low_similarity",

        "risk_category": "modified_clause",
        "severity": "high",

        "legal_reference": None,

        "description": (
            "A modified renewal clause with low similarity "
            "to the approved reference clause should be reviewed."
        ),

        "required_terms": [],
        "forbidden_terms": [],
        "risk_terms": [],

        "use_is_modified": True,
        "similarity_threshold": 0.90,
    },


    # =========================================================
    # R006 - Modified Confidentiality
    # =========================================================

    {
        "rule_id": "R006",
        "clause_type": "Confidentiality",
        "rule_type": "engineering_rule",
        "trigger": "modified_confidentiality",

        "risk_category": "modified_clause",
        "severity": "medium",

        "legal_reference": None,

        "description": (
            "A modified confidentiality clause should be reviewed "
            "against the approved reference clause."
        ),

        "required_terms": [],
        "forbidden_terms": [],
        "risk_terms": [],

        "use_is_modified": True,
    },


    # =========================================================
    # R007 - Risky Payment Terms
    # =========================================================

    {
    "rule_id": "R007",
    "rule_type": "engineering_rule",
    "clause_type": "Payment",
    "trigger": "risky_payment_terms",
    "risk_category": "risky_clause",
    "severity": "medium",
    "description": (
        "Payment clauses containing penalty, delay, late payment, or "
        "interest conditions should be reviewed."
    ),
    "required_terms": [],
    # ---------------------------------------------------------
    # بدايه التعديل الثاني      
    # --------------------------------------------------------
    # "forbidden_terms": [
    #     "no penalty",
    #     "no penalties",
    #     "without penalty",
    #     "no interest",
    #     "without interest",
    #     "no late payment",
    #     "without late payment",
    # ],
    # "risk_terms": [
    #     "penalty",
    #     "late payment",
    #     "delay",
    #     "interest",
    # ],

    # ---------------------------------------------------------
    # بدايه نص التعديل 
    # ---------------------------------------------------------
        "forbidden_terms": [
        "no penalty",
        "no penalties",
        "without penalty",
        "no interest",
        "without interest",
        "no late payment",
        "without late payment",
        "بدون غرامة",
        "دون غرامة",
        "بدون فائدة",
        "دون فائدة",
    ],
    "risk_terms": [
        "penalty",
        "late payment",
        "delay",
        "interest",
        "غرامة",
        "تأخير في السداد",
        "تأخير السداد",
        "تأخير",
        "فائدة",
    ],
    # ---------------------------------------------------------
    # نهايه نص التعديل
    # --------------------------------------------------------- 
    "legal_reference": None,
},


    # =========================================================
    # R008 - Modified Liability
    # =========================================================

    {
        "rule_id": "R008",
        "clause_type": "Liability",
        "rule_type": "engineering_rule",
        "trigger": "modified_liability",

        "risk_category": "modified_clause",
        "severity": "high",

        "legal_reference": None,

        "description": (
            "A modified liability clause should be reviewed "
            "against the approved reference clause."
        ),

        "required_terms": [],
        "forbidden_terms": [],
        "risk_terms": [],

        "use_is_modified": True,
    },


    # =========================================================
    # R009 - Modified Governing Law
    # =========================================================

    {
        "rule_id": "R009",
        "clause_type": "Governing Law",
        "rule_type": "engineering_rule",
        "trigger": "modified_governing_law",

        "risk_category": "modified_clause",
        "severity": "high",

        "legal_reference": None,

        "description": (
            "A modified governing law clause should be reviewed "
            "against the approved reference clause."
        ),

        "required_terms": [],
        "forbidden_terms": [],
        "risk_terms": [],

        "use_is_modified": True,
    },


    # =========================================================
    # R010 - Modified Dispute Resolution
    # =========================================================

    {
        "rule_id": "R010",
        "clause_type": "Dispute Resolution",
        "rule_type": "engineering_rule",
        "trigger": "modified_dispute_resolution",

        "risk_category": "modified_clause",
        "severity": "high",

        "legal_reference": None,

        "description": (
            "A modified dispute resolution clause should be reviewed "
            "against the approved reference clause."
        ),

        "required_terms": [],
        "forbidden_terms": [],
        "risk_terms": [],

        "use_is_modified": True,
    },


    # =========================================================
    # R011 - Unusual Termination
    # =========================================================

    {
        "rule_id": "R011",
        "clause_type": "Termination",
        "rule_type": "engineering_rule",
        "trigger": "unusual_termination",

        "risk_category": "unusual_clause",
        "severity": "medium",

        "legal_reference": None,

        "description": (
            "An unusual termination clause should be reviewed "
            "against the approved reference clause."
        ),

        "required_terms": [],
        "forbidden_terms": [],

        # ---------------------------------------------------------
        # بدايه التعديل الثالث
        # --------------------------------------------------------- 

        # "risk_terms": [
        #     "immediately",
        #     "at any time",
        #     "without cause",
        # ],
        # ---------------------------------------------------------
        # نص التعديل الثالث
        # --------------------------------------------------------- 
                "risk_terms": [
            "immediately",
            "at any time",
            "without cause",
            "فورا",
            "فوريا",
            "في أي وقت",
            "دون سبب",
            "بدون سبب",
        ],
        # ---------------------------------------------------------
        # نهايه نص التعديل الثالث       
        # ---------------------------------------------------------
    },


    # =========================================================
    # R012 - Unusual Liability
    # =========================================================

    {
        "rule_id": "R012",
        "clause_type": "Liability",
        "rule_type": "engineering_rule",
        "trigger": "unusual_liability",

        "risk_category": "unusual_clause",
        "severity": "high",

        "legal_reference": None,

        "description": (
            "An unusual limitation or exclusion of liability "
            "should be reviewed."
        ),

        "required_terms": [],
        "forbidden_terms": [],
    # ---------------------------------------------------------
    # بدايه التعديل الرابع
    # ---------------------------------------------------------
        # "risk_terms": [
        #     "no liability",
        #     "unlimited liability",
        #     "exclude all liability",
        #     "sole liability",
        # ],

        # ---------------------------------------------------------
        # نص  التعديل الرابع
        # ---------------------------------------------------------
                "risk_terms": [
            "no liability",
            "unlimited liability",
            "exclude all liability",
            "sole liability",
            "دون مسؤولية",
            "بدون مسؤولية",
            "مسؤولية غير محدودة",
            "مسؤولية كاملة",
            "استبعاد المسؤولية",
        ],
        # ---------------------------------------------------------
        # نهايه نص التعديل الرابع
        # ---------------------------------------------------------
    },


    # =========================================================
    # R013 - Modified Payment
    # =========================================================

    {
        "rule_id": "R013",
        "clause_type": "Payment",
        "rule_type": "engineering_rule",
        "trigger": "modified_payment",

        "risk_category": "modified_clause",
        "severity": "medium",

        "legal_reference": None,

        "description": (
            "A modified payment clause should be reviewed "
            "against the approved reference clause."
        ),

        "required_terms": [],
        "forbidden_terms": [],
        "risk_terms": [],

        "use_is_modified": True,
    },


    # =========================================================
    # R014 - Modified Penalty
    # =========================================================

    {
        "rule_id": "R014",
        "clause_type": "Penalty",
        "rule_type": "engineering_rule",
        "trigger": "modified_penalty",

        "risk_category": "modified_clause",
        "severity": "high",

        "legal_reference": None,

        "description": (
            "A modified penalty clause should be reviewed "
            "against the approved reference clause."
        ),

        "required_terms": [],
        "forbidden_terms": [],
        "risk_terms": [],

        "use_is_modified": True,
    },

    # بدايه الاضافه للتعديل

    # =========================================================
    # R014 - Unbalanced Indemnity
    # =========================================================

    {
        "rule_id": "R014",
        "clause_type": "Indemnity",
        "rule_type": "risky_clause",
        "trigger": "unbalanced_indemnity",

        "risk_category": "risky_clause",
        "severity": "high",

        "legal_reference": None,

        "description": (
            "An indemnity clause that requires one party to cover losses "
            "even where caused in part by the other party's own fault "
            "should be reviewed."
        ),

        "required_terms": [],
        "forbidden_terms": [],

        "risk_terms": [
            "even if",
            "regardless of fault",
            "حتى إذا ساهم",
            "حتى لو ساهم",
            "حتى إن ساهم",
            "بصرف النظر عن الخطأ",
        ],
    },
    # ---------------------------------------------------------
    # نهاية التعديل 
    # ---------------------------------------------------------


    # =========================================================
    # R015 - Unusual Confidentiality Disclosure
    # =========================================================

    {
        "rule_id": "R015",
        "clause_type": "Confidentiality",
        "rule_type": "engineering_rule",
        "trigger": "unusual_disclosure",

        "risk_category": "unusual_clause",
        "severity": "medium",

        "legal_reference": None,

        "description": (
            "An unusual confidentiality disclosure condition "
            "should be reviewed."
        ),

        "required_terms": [],
        "forbidden_terms": [],

        "risk_terms": [
            "third party",
            "public disclosure",
            "without consent",
        ],
    },


    # =========================================================
    # بداية التعديل 
    # =========================================================

    # =========================================================
    # R015 - IP Transfer Without Compensation
    # =========================================================

    {
        "rule_id": "R015",
        "clause_type": "Intellectual Property",
        "rule_type": "risky_clause",
        "trigger": "ip_transfer_no_compensation",

        "risk_category": "risky_clause",
        "severity": "high",

        "legal_reference": None,

        "description": (
            "A clause transferring intellectual property rights without "
            "additional compensation should be reviewed."
        ),

        "required_terms": [],
        "forbidden_terms": [],

        "risk_terms": [
            "without additional compensation",
            "no additional payment",
            "دون مقابل",
            "بدون مقابل",
            "دون مقابل إضافي",
        ],
    },


]