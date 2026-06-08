"""Tests for tribl Pydantic models."""

import json

import pytest
from pydantic import ValidationError

from tribl.models import (
    Approach,
    Confidence,
    RepoQuality,
    RexItem,
    RexReport,
)


class TestApproach:
    def test_create_minimal(self):
        a = Approach(description="Use caching", details="Added Redis caching layer")
        assert a.description == "Use caching"
        assert a.worked is None
        assert a.details == "Added Redis caching layer"

    def test_create_with_worked(self):
        a = Approach(description="Use caching", worked=True, details="Improved latency by 50%")
        assert a.worked is True

    def test_serialization_roundtrip(self):
        a = Approach(description="desc", worked=False, details="details")
        data = a.model_dump()
        a2 = Approach.model_validate(data)
        assert a == a2


class TestConfidence:
    def test_values(self):
        assert Confidence.STRONGLY_INFERRED.value == "fortement_infere"
        assert Confidence.PROBABLE.value == "probable"
        assert Confidence.CAUTIOUS_HYPOTHESIS.value == "hypothese_prudente"
        assert Confidence.INSUFFICIENT_SIGNAL.value == "signal_insuffisant"

    def test_from_value(self):
        c = Confidence("probable")
        assert c == Confidence.PROBABLE


class TestRepoQuality:
    def test_values(self):
        assert RepoQuality.GOOD.value == "bon"
        assert RepoQuality.ACCEPTABLE.value == "correct"
        assert RepoQuality.INSUFFICIENT.value == "insuffisant"


class TestRexItem:
    def test_create_full(self):
        rex = RexItem(
            theme="Error Handling",
            context="REST API service",
            problem="Inconsistent error responses across endpoints",
            approaches=[
                Approach(
                    description="Global exception handler",
                    worked=True,
                    details="Centralized error formatting in middleware",
                ),
                Approach(
                    description="Per-endpoint try/catch",
                    worked=False,
                    details="Led to duplicated code and inconsistencies",
                ),
            ],
            result="Unified error response format adopted",
            learning="Centralized error handling reduces inconsistencies and duplication",
            recommendation="Implement a global exception handler middleware early in the project",
            confidence=Confidence.STRONGLY_INFERRED,
            source_files=["src/middleware/error_handler.py", "src/api/routes.py"],
            tags=["error-handling", "middleware", "api"],
        )
        assert rex.theme == "Error Handling"
        assert len(rex.approaches) == 2
        assert rex.approaches[0].worked is True
        assert rex.confidence == Confidence.STRONGLY_INFERRED

    def test_create_minimal(self):
        rex = RexItem(
            theme="Testing",
            context="Unit tests",
            problem="No tests",
            approaches=[],
            learning="Tests are important",
            recommendation="Add tests",
            confidence=Confidence.INSUFFICIENT_SIGNAL,
            source_files=[],
            tags=[],
        )
        assert rex.result is None
        assert rex.approaches == []

    def test_invalid_confidence_rejected(self):
        with pytest.raises(ValidationError):
            RexItem(
                theme="T",
                context="C",
                problem="P",
                approaches=[],
                learning="L",
                recommendation="R",
                confidence="invalid_value",  # type: ignore[arg-type]
                source_files=[],
                tags=[],
            )


class TestRexReport:
    def _make_report(self, **overrides) -> RexReport:
        defaults = {
            "repo_name": "test-repo",
            "repo_path": "/tmp/test-repo",
            "analyzed_at": "2024-01-15T10:30:00Z",
            "model_used": "claude-sonnet-4-6",
            "files_scanned": 42,
            "repo_quality": RepoQuality.GOOD,
            "warnings": [],
            "rex_items": [],
            "global_summary": "A well-structured repository.",
            "strengths": ["Good test coverage"],
            "improvement_suggestions": ["Add type hints"],
        }
        defaults.update(overrides)
        return RexReport(**defaults)

    def test_create_minimal(self):
        report = self._make_report()
        assert report.repo_name == "test-repo"
        assert report.files_scanned == 42
        assert report.repo_quality == RepoQuality.GOOD

    def test_with_rex_items(self):
        rex = RexItem(
            theme="Architecture",
            context="Monolith",
            problem="Tight coupling",
            approaches=[
                Approach(description="Extract service", worked=True, details="Decoupled auth"),
            ],
            learning="Loose coupling enables independent deployment",
            recommendation="Use dependency injection",
            confidence=Confidence.PROBABLE,
            source_files=["src/auth/service.py"],
            tags=["architecture"],
        )
        report = self._make_report(rex_items=[rex])
        assert len(report.rex_items) == 1
        assert report.rex_items[0].theme == "Architecture"

    def test_json_roundtrip(self):
        report = self._make_report(
            warnings=["Limited test files found"],
            rex_items=[
                RexItem(
                    theme="CI/CD",
                    context="GitHub Actions",
                    problem="No caching",
                    approaches=[
                        Approach(
                            description="Add cache step",
                            worked=True,
                            details="Used actions/cache",
                        ),
                    ],
                    result="Build time reduced by 60%",
                    learning="CI caching is essential for fast feedback",
                    recommendation="Cache dependencies in CI pipelines",
                    confidence=Confidence.STRONGLY_INFERRED,
                    source_files=[".github/workflows/ci.yml"],
                    tags=["ci", "performance"],
                ),
            ],
        )
        json_str = report.model_dump_json()
        data = json.loads(json_str)
        report2 = RexReport.model_validate(data)
        assert report == report2

    def test_invalid_quality_rejected(self):
        with pytest.raises(ValidationError):
            self._make_report(repo_quality="invalid")  # type: ignore[arg-type]

    def test_json_schema_generation(self):
        schema = RexReport.model_json_schema()
        assert "properties" in schema
        assert "repo_name" in schema["properties"]
        assert "rex_items" in schema["properties"]
