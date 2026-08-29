from src.schemas.m6_contract import ContractClause
from src.risk_engine.engine.risk_engine import analyze_clause

test_cases = [

    # =========================================================
    # R001 - Termination / Breach without notice
    # =========================================================

    {
        "name": "Termination - breach without notice",
        "clause": ContractClause(
            clause_id="T001",
            type="Termination",
            text=(
                "Either party may terminate the contract "
                "if the other party breaches its obligations."
            ),
            entities={},
            page=1,
            similarity_score=0.80,
            is_modified=True,
            confidence=0.90,
        ),
        "expected_risk": True,
        "expected_rule": "R001",
    },

    {
        "name": "Termination - breach with notice",
        "clause": ContractClause(
            clause_id="T002",
            type="Termination",
            text=(
                "Either party may terminate the contract "
                "after providing thirty days notice if the other "
                "party breaches its obligations."
            ),
            entities={},
            page=2,
            similarity_score=0.80,
            is_modified=True,
            confidence=0.90,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },

    {
        "name": "Termination - normal notice",
        "clause": ContractClause(
            clause_id="T003",
            type="Termination",
            text=(
                "Either party may terminate the contract "
                "by providing written notice."
            ),
            entities={},
            page=3,
            similarity_score=0.93,
            is_modified=False,
            confidence=0.96,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },


    # =========================================================
    # R002 - Penalty / Article 224
    # =========================================================

    {
        "name": "Penalty - agreed penalty",
        "clause": ContractClause(
            clause_id="P001",
            type="Penalty",
            text=(
                "The party shall pay a penalty of "
                "500,000 EGP for failure to perform."
            ),
            entities={"amount": "500000 EGP"},
            page=5,
            similarity_score=0.75,
            is_modified=True,
            confidence=0.88,
        ),
        "expected_risk": True,
        "expected_rule": "R002",
    },

    {
        "name": "Penalty - normal compensation",
        "clause": ContractClause(
            clause_id="P002",
            type="Penalty",
            text=(
                "The parties may agree on compensation "
                "for proven damages."
            ),
            entities={},
            page=6,
            similarity_score=0.90,
            is_modified=False,
            confidence=0.92,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },

    {
        "name": "Penalty - no penalty",
        "clause": ContractClause(
            clause_id="P003",
            type="Penalty",
            text=(
                "The parties shall discuss compensation "
                "for actual damages."
            ),
            entities={},
            page=7,
            similarity_score=0.92,
            is_modified=False,
            confidence=0.94,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },


    # =========================================================
    # R003 - Undue Payment / Article 181
    # =========================================================

    {
        "name": "Payment - amount not due",
        "clause": ContractClause(
            clause_id="PAY001",
            type="Payment",
            text=(
                "Any amount paid but not due under the contract "
                "shall be reviewed and returned."
            ),
            entities={},
            page=8,
            similarity_score=0.80,
            is_modified=False,
            confidence=0.90,
        ),
        "expected_risk": True,
        "expected_rule": "R003",
    },

    {
        "name": "Payment - normal payment",
        "clause": ContractClause(
            clause_id="PAY002",
            type="Payment",
            text=(
                "Payment shall be made within 30 days "
                "of receiving the invoice."
            ),
            entities={"payment_period": "30 days"},
            page=9,
            similarity_score=0.91,
            is_modified=False,
            confidence=0.94,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },


    # =========================================================
    # R004 / R005 - Renewal
    # =========================================================

    {
        "name": "Renewal - modified",
        "clause": ContractClause(
            clause_id="R001",
            type="Renewal",
            text=(
                "The contract shall automatically renew "
                "for 5 years."
            ),
            entities={"duration": "5 years"},
            page=10,
            similarity_score=0.82,
            is_modified=True,
            confidence=0.79,
        ),
        "expected_risk": True,
        "expected_rule": "R004",
    },

    {
        "name": "Renewal - modified low similarity",
        "clause": ContractClause(
            clause_id="R002",
            type="Renewal",
            text=(
                "The agreement shall automatically renew "
                "for another three years."
            ),
            entities={"duration": "3 years"},
            page=11,
            similarity_score=0.81,
            is_modified=True,
            confidence=0.84,
        ),
        "expected_risk": True,
        "expected_rule": "R004",
    },

    {
        "name": "Renewal - unchanged",
        "clause": ContractClause(
            clause_id="R003",
            type="Renewal",
            text=(
                "The contract shall automatically renew "
                "according to the agreed terms."
            ),
            entities={},
            page=12,
            similarity_score=0.98,
            is_modified=False,
            confidence=0.96,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },


    # =========================================================
    # R006 / R015 - Confidentiality
    # =========================================================

    {
        "name": "Confidentiality - modified",
        "clause": ContractClause(
            clause_id="C001",
            type="Confidentiality",
            text=(
                "Each party shall keep confidential information "
                "and shall not disclose it without authorization."
            ),
            entities={},
            page=13,
            similarity_score=0.70,
            is_modified=True,
            confidence=0.90,
        ),
        "expected_risk": True,
        "expected_rule": "R006",
    },

    {
        "name": "Confidentiality - normal",
        "clause": ContractClause(
            clause_id="C002",
            type="Confidentiality",
            text=(
                "Each party shall keep confidential information "
                "and shall not disclose it without authorization."
            ),
            entities={},
            page=14,
            similarity_score=0.93,
            is_modified=False,
            confidence=0.96,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },

    {
        "name": "Confidentiality - third party disclosure",
        "clause": ContractClause(
            clause_id="C003",
            type="Confidentiality",
            text=(
                "Confidential information may be disclosed "
                "to selected third parties."
            ),
            entities={},
            page=15,
            similarity_score=0.72,
            is_modified=False,
            confidence=0.85,
        ),
        "expected_risk": True,
        "expected_rule": "R015",
    },


    # =========================================================
    # R007 - Risky Payment Terms
    # =========================================================

    {
        "name": "Payment - late payment penalty",
        "clause": ContractClause(
            clause_id="PAY003",
            type="Payment",
            text=(
                "Late payment shall result in a penalty "
                "of 10 percent."
            ),
            entities={"penalty": "10 percent"},
            page=16,
            similarity_score=0.75,
            is_modified=True,
            confidence=0.86,
        ),
        "expected_risk": True,
        "expected_rule": "R007",
    },

    {
        "name": "Payment - interest",
        "clause": ContractClause(
            clause_id="PAY004",
            type="Payment",
            text=(
                "Interest shall apply to any late payment."
            ),
            entities={"interest": "late payment"},
            page=17,
            similarity_score=0.76,
            is_modified=True,
            confidence=0.87,
        ),
        "expected_risk": True,
        "expected_rule": "R007",
    },

    {
        "name": "Payment - normal bank transfer",
        "clause": ContractClause(
            clause_id="PAY005",
            type="Payment",
            text=(
                "Payment shall be made by bank transfer "
                "within 15 days."
            ),
            entities={"payment_period": "15 days"},
            page=18,
            similarity_score=0.94,
            is_modified=False,
            confidence=0.95,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },


    # =========================================================
    # R008 - Liability
    # =========================================================

    {
        "name": "Liability - modified",
        "clause": ContractClause(
            clause_id="L001",
            type="Liability",
            text=(
                "The liability of either party shall be "
                "limited according to the terms of this agreement."
            ),
            entities={},
            page=19,
            similarity_score=0.70,
            is_modified=True,
            confidence=0.90,
        ),
        "expected_risk": True,
        "expected_rule": "R008",
    },

    {
        "name": "Liability - normal",
        "clause": ContractClause(
            clause_id="L002",
            type="Liability",
            text=(
                "Each party shall be liable for losses "
                "caused by its breach."
            ),
            entities={},
            page=20,
            similarity_score=0.95,
            is_modified=False,
            confidence=0.96,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },

    {
        "name": "Liability - no liability",
        "clause": ContractClause(
            clause_id="L003",
            type="Liability",
            text=(
                "The supplier shall have no liability "
                "for any loss."
            ),
            entities={},
            page=21,
            similarity_score=0.90,
            is_modified=False,
            confidence=0.92,
        ),
        "expected_risk": True,
        "expected_rule": "R012",
    },


    # =========================================================
    # R009 - Governing Law
    # =========================================================

    {
        "name": "Governing Law - modified",
        "clause": ContractClause(
            clause_id="G001",
            type="Governing Law",
            text=(
                "This agreement shall be governed by "
                "the laws of England."
            ),
            entities={"country": "England"},
            page=22,
            similarity_score=0.70,
            is_modified=True,
            confidence=0.90,
        ),
        "expected_risk": True,
        "expected_rule": "R009",
    },

    {
        "name": "Governing Law - unchanged",
        "clause": ContractClause(
            clause_id="G002",
            type="Governing Law",
            text=(
                "This agreement shall be governed by "
                "the laws of Egypt."
            ),
            entities={"country": "Egypt"},
            page=23,
            similarity_score=0.98,
            is_modified=False,
            confidence=0.97,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },


    # =========================================================
    # R010 - Dispute Resolution
    # =========================================================

    {
        "name": "Dispute Resolution - modified",
        "clause": ContractClause(
            clause_id="D001",
            type="Dispute Resolution",
            text=(
                "Any dispute shall be resolved through "
                "international arbitration."
            ),
            entities={},
            page=24,
            similarity_score=0.70,
            is_modified=True,
            confidence=0.89,
        ),
        "expected_risk": True,
        "expected_rule": "R010",
    },

    {
        "name": "Dispute Resolution - unchanged",
        "clause": ContractClause(
            clause_id="D002",
            type="Dispute Resolution",
            text=(
                "Any dispute shall be resolved by the "
                "competent courts."
            ),
            entities={},
            page=25,
            similarity_score=0.97,
            is_modified=False,
            confidence=0.96,
        ),
        "expected_risk": False,
        "expected_rule": None,
    },


    # =========================================================
    # R011 - Unusual Termination
    # =========================================================

    {
        "name": "Termination - immediately",
        "clause": ContractClause(
            clause_id="T005",
            type="Termination",
            text=(
                "Either party may immediately terminate "
                "the contract."
            ),
            entities={},
            page=26,
            similarity_score=0.90,
            is_modified=False,
            confidence=0.91,
        ),
        "expected_risk": True,
        "expected_rule": "R011",
    },


    # =========================================================
    # R013 - Modified Payment
    # =========================================================

    {
        "name": "Payment - modified",
        "clause": ContractClause(
            clause_id="PAY006",
            type="Payment",
            text=(
                "Payment shall be made within 60 days "
                "of receiving the invoice."
            ),
            entities={"payment_period": "60 days"},
            page=27,
            similarity_score=0.70,
            is_modified=True,
            confidence=0.90,
        ),
        "expected_risk": True,
        "expected_rule": "R013",
    },


    # =========================================================
    # R014 - Modified Penalty
    # =========================================================

    {
        "name": "Penalty - modified",
        "clause": ContractClause(
            clause_id="P004",
            type="Penalty",
            text=(
                "The party shall pay a penalty of "
                "100,000 EGP for failure to perform."
            ),
            entities={"amount": "100000 EGP"},
            page=28,
            similarity_score=0.70,
            is_modified=True,
            confidence=0.90,
        ),
        "expected_risk": True,
        "expected_rule": "R002",
    },
]


def run_evaluation():

    total = len(test_cases)

    correct = 0
    true_positive = 0
    true_negative = 0
    false_positive = 0
    false_negative = 0

    print("=" * 70)
    print("M6 RISK ENGINE EVALUATION")
    print("=" * 70)

    for case in test_cases:

        risks = analyze_clause(case["clause"])

        actual_risk = len(risks) > 0
        expected_risk = case["expected_risk"]

        actual_rules = [
            risk.rule_id
            for risk in risks
        ]

        expected_rule = case["expected_rule"]

        rule_match = (
            expected_rule is None
            or expected_rule in actual_rules
        )

        # -----------------------------------------------------
        # Confusion matrix
        # -----------------------------------------------------

        if expected_risk and actual_risk:
            true_positive += 1

        elif not expected_risk and not actual_risk:
            true_negative += 1

        elif not expected_risk and actual_risk:
            false_positive += 1

        elif expected_risk and not actual_risk:
            false_negative += 1

        # -----------------------------------------------------
        # Correctness
        # -----------------------------------------------------

        is_correct = (
            actual_risk == expected_risk
            and rule_match
        )

        if is_correct:
            correct += 1

        print("-" * 70)
        print(case["name"])
        print(f"Expected Risk:  {expected_risk}")
        print(f"Actual Risk:    {actual_risk}")
        print(f"Expected Rule:  {expected_rule}")
        print(f"Actual Rules:   {actual_rules}")
        print(f"Correct:        {is_correct}")

        if not is_correct:
            print("!!! TEST FAILED !!!")

    # ---------------------------------------------------------
    # Metrics
    # ---------------------------------------------------------

    accuracy = correct / total if total else 0

    if true_positive + false_positive > 0:
        precision = true_positive / (
            true_positive + false_positive
        )
    else:
        precision = 0

    if true_positive + false_negative > 0:
        recall = true_positive / (
            true_positive + false_negative
        )
    else:
        recall = 0

    if precision + recall > 0:
        f1 = (
            2
            * (precision * recall)
            / (precision + recall)
        )
    else:
        f1 = 0

    # ---------------------------------------------------------
    # Final report
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("FINAL EVALUATION RESULTS")
    print("=" * 70)

    print(f"Total cases:       {total}")
    print(f"Correct:            {correct}")
    print(f"Accuracy:           {accuracy:.2%}")

    print("\nConfusion Matrix:")
    print(f"True Positives:     {true_positive}")
    print(f"True Negatives:     {true_negative}")
    print(f"False Positives:    {false_positive}")
    print(f"False Negatives:    {false_negative}")

    print("\nMetrics:")
    print(f"Precision:           {precision:.2%}")
    print(f"Recall:              {recall:.2%}")
    print(f"F1 Score:            {f1:.2%}")


if __name__ == "__main__":
    run_evaluation()