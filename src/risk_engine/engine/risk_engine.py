from src.schemas.m6_contract import ContractClause, ContractRisk
from src.risk_engine.rules.legal_playbook import RULES


def matches_rule(clause: ContractClause, rule: dict) -> bool:
    """
    Check whether a specific rule applies to a contract clause.
    """

    # ---------------------------------------------------------
    # 1. Clause type must match
    # ---------------------------------------------------------
    if clause.type != rule["clause_type"]:
        return False

    text = clause.text.lower()

    # ---------------------------------------------------------
    # 2. Required terms
    # ---------------------------------------------------------
    for term in rule.get("required_terms", []):
        if term.lower() not in text:
            return False

    # ---------------------------------------------------------
    # 3. Forbidden terms
    # ---------------------------------------------------------
    for term in rule.get("forbidden_terms", []):
        if term.lower() in text:
            return False

    # ---------------------------------------------------------
    # 4. Risk terms
    # ---------------------------------------------------------
    risk_terms = rule.get("risk_terms", [])

    if risk_terms:
        if not any(term.lower() in text for term in risk_terms):
            return False

    # ---------------------------------------------------------
    # 5. Modified clause rules
    # ---------------------------------------------------------
    if rule.get("use_is_modified"):

        if not clause.is_modified:
            return False

    # ---------------------------------------------------------
    # 6. Similarity threshold
    # ---------------------------------------------------------
    if "similarity_threshold" in rule:

        threshold = rule["similarity_threshold"]

        if clause.similarity_score >= threshold:
            return False

    # ---------------------------------------------------------
    # 7. Special trigger:
    #    Termination because of breach without notice
    # ---------------------------------------------------------
    if rule["trigger"] == "breach_without_notice":

        has_breach = "breach" in text
        has_terminate = "terminate" in text
        has_notice = "notice" in text

        return (
            has_breach
            and has_terminate
            and not has_notice
        )

    # ---------------------------------------------------------
    # 8. Special trigger:
    #    Undue payment
    # ---------------------------------------------------------
    if rule["trigger"] == "undue_payment":

        undue_payment_terms = [
            "not due",
            "undue",
            "not legally owed",
            "not owed",
        ]

        return any(
            term in text
            for term in undue_payment_terms
        )

    # ---------------------------------------------------------
    # 9. Known triggers that are already handled by
    #    generic conditions above
    # ---------------------------------------------------------
    known_triggers = {
        "modified_renewal",
        "modified_renewal_low_similarity",
        "modified_confidentiality",
        "modified_liability",
        "modified_governing_law",
        "modified_dispute_resolution",
        "modified_payment",
        "modified_penalty",
        "unusual_termination",
        "unusual_liability",
        "unusual_disclosure",
        "risky_payment_terms",
        "agreed_compensation",
    }

    if rule["trigger"] in known_triggers:
        return True

    # ---------------------------------------------------------
    # 10. Unknown trigger
    #
    # VERY IMPORTANT:
    # Never assume an unknown trigger matches.
    # ---------------------------------------------------------
    return False


def create_risk(
    clause: ContractClause,
    rule: dict
) -> ContractRisk:
    """
    Convert a matched rule into a ContractRisk object.
    """

    review_status = "pending"

    # Low confidence means that human verification is recommended.
    if clause.confidence < 0.70:
        review_status = "needs_verification"

    return ContractRisk(
        risk=rule["risk_category"],
        severity=rule["severity"],
        explanation=rule["description"],
        evidence=clause.text,
        page=clause.page,
        clause=clause.clause_id,
        confidence=clause.confidence,
        review_status=review_status,

        # Rule provenance
        rule_id=rule["rule_id"],
        rule_type=rule["rule_type"],
        legal_reference=rule.get("legal_reference"),
    )


def analyze_clause(clause: ContractClause):
    """
    Apply all M6 rules to one ContractClause.
    """

    risks = []

    for rule in RULES:

        if matches_rule(clause, rule):

            risk = create_risk(
                clause,
                rule
            )

            risks.append(risk)

    return risks