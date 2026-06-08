"""Pydantic v2 models for tribl analysis reports."""

from enum import Enum

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    """Confidence level for a REX item."""

    STRONGLY_INFERRED = "fortement_infere"
    PROBABLE = "probable"
    CAUTIOUS_HYPOTHESIS = "hypothese_prudente"
    INSUFFICIENT_SIGNAL = "signal_insuffisant"


class RepoQuality(str, Enum):
    """Overall quality assessment of the analyzed repository."""

    GOOD = "bon"
    ACCEPTABLE = "correct"
    INSUFFICIENT = "insuffisant"


class Approach(BaseModel):
    """An approach tried to solve a problem, as observed in the code."""

    description: str = Field(description="Brief description of the approach")
    worked: bool | None = Field(
        default=None, description="Whether this approach worked (None if unclear)"
    )
    details: str = Field(description="Detailed explanation with code evidence")


class RexItem(BaseModel):
    """A single REX (Retour d'EXperience / lesson learned) extracted from the code."""

    theme: str = Field(description="High-level theme (e.g., 'Error Handling', 'Testing')")
    context: str = Field(description="Context in which this lesson applies")
    problem: str = Field(description="The problem or challenge encountered")
    approaches: list[Approach] = Field(description="Approaches tried (tripartite structure)")
    result: str | None = Field(default=None, description="Outcome of the chosen approach")
    learning: str = Field(description="The key learning / takeaway")
    recommendation: str = Field(description="Actionable recommendation")
    confidence: Confidence = Field(description="Confidence level of this REX")
    source_files: list[str] = Field(description="Files that evidence this REX")
    tags: list[str] = Field(description="Tags for categorization")


class RexReport(BaseModel):
    """Complete analysis report for a repository."""

    repo_name: str = Field(description="Name of the analyzed repository")
    repo_path: str = Field(description="Absolute path to the repository")
    analyzed_at: str = Field(description="ISO 8601 timestamp of analysis")
    model_used: str = Field(description="Claude model used for analysis")
    files_scanned: int = Field(description="Number of files scanned")
    repo_quality: RepoQuality = Field(description="Overall repository quality")
    warnings: list[str] = Field(
        default_factory=list, description="Warnings about analysis limitations"
    )
    rex_items: list[RexItem] = Field(default_factory=list, description="Extracted REX items")
    global_summary: str = Field(description="High-level summary of findings")
    strengths: list[str] = Field(default_factory=list, description="Repository strengths")
    improvement_suggestions: list[str] = Field(
        default_factory=list, description="Suggestions for improvement"
    )
