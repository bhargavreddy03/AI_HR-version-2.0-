"""Pydantic v2 DTOs for Skill Registry and Extraction Contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class SkillDefinitionDTO(BaseModel):
    """Canonical representation of a verified skill entity."""

    model_config = ConfigDict(frozen=True)

    skill_id: str = Field(..., description="Stable, URL-safe canonical skill identifier")
    canonical_name: str = Field(..., description="Standardized display name")
    category: str = Field(..., description="Domain competency category")
    aliases: list[str] = Field(default_factory=list, description="Verified alternative names and aliases")

    @property
    def domain(self) -> str:
        """Alias for category for domain taxonomy parity."""
        return self.category


class CollisionReportDTO(BaseModel):
    """Auditable collision report when an alias maps to multiple canonical candidates."""

    model_config = ConfigDict(frozen=True)

    alias: str = Field(..., description="The conflicting alias term")
    primary_canonical: str = Field(..., description="Deterministically chosen canonical owner")
    conflicting_canonicals: list[str] = Field(..., description="All canonical candidates claiming this alias")
    resolution_strategy: str = Field(default="first_registered", description="Deterministic resolution rule applied")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaxonomySummaryReportDTO(BaseModel):
    """Aggregate collision report summary across the entire taxonomy."""

    model_config = ConfigDict(frozen=True)

    total_collisions: int = Field(default=0, ge=0)
    collision_details: list[CollisionReportDTO] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaxonomyMetadataDTO(BaseModel):
    """Taxonomy release metadata and governance statistics."""

    model_config = ConfigDict(frozen=True)

    version: str = Field(..., description="Taxonomy release version string")
    source_provenance: str = Field(..., description="Originating repository and source")
    total_categories: int = Field(..., ge=0)
    total_canonical_skills: int = Field(..., ge=0)
    total_indexed_aliases: int = Field(..., ge=0)
    detected_collisions_count: int = Field(default=0, ge=0)
    category_list: list[str] = Field(default_factory=list)

    @property
    def total_domains(self) -> int:
        return self.total_categories

    @property
    def domains(self) -> list[str]:
        return self.category_list

    @property
    def total_aliases(self) -> int:
        return self.total_indexed_aliases

    @property
    def total_collisions(self) -> int:
        return self.detected_collisions_count


class SkillMatchResultDTO(BaseModel):
    """Result of a single extracted skill occurrence."""

    model_config = ConfigDict(frozen=True)

    skill_id: str
    canonical_name: str
    category: str
    matched_term: str
    is_exact_canonical: bool = False
    start_char: int = Field(default=0, ge=0)
    end_char: int = Field(default=0, ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def domain(self) -> str:
        return self.category

    @property
    def raw_match(self) -> str:
        return self.matched_term


class SkillExtractionResultDTO(BaseModel):
    """Complete output contract for deterministic skill extraction."""

    model_config = ConfigDict(frozen=True)

    extracted_skills: list[SkillMatchResultDTO]
    total_matches: int
    matched_categories: list[str]
    categorized_breakdown: dict[str, list[str]]

    @property
    def skills(self) -> list[SkillMatchResultDTO]:
        return self.extracted_skills

    @property
    def total_unique_skills(self) -> int:
        return self.total_matches

    @property
    def domains_represented(self) -> list[str]:
        return self.matched_categories

    @property
    def domain_breakdown(self) -> dict[str, list[str]]:
        return self.categorized_breakdown
