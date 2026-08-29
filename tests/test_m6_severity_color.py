import unittest

from src.schemas.m6_contract import ContractRisk

def make_risk(severity: str) -> ContractRisk:
    return ContractRisk(
        risk="risky_clause",
        severity=severity,
        explanation="Review required.",
        evidence="Example clause.",
        page=1,
        clause="C001",
        confidence=0.9,
        review_status="pending",
        rule_id="R001",
        rule_type="legal_rule",
    )


class TestSeverityColor(unittest.TestCase):

    def test_severity_color_mapping(self):
        cases = [
            ("low", "green"),
            ("medium", "yellow"),
            ("high", "red"),
            ("critical", "dark_red"),
            ("unknown", "gray"),
            ("HIGH", "red"),
        ]

        for severity, expected_color in cases:
            with self.subTest(severity=severity):
                self.assert_mapping(severity, expected_color)

    def assert_mapping(self, severity: str, expected_color: str):
        risk = make_risk(severity)

        self.assertEqual(risk.severity, severity)
        self.assertEqual(risk.severity_color, expected_color)
        self.assertEqual(
            risk.model_dump()["severity_color"],
            expected_color,
        )