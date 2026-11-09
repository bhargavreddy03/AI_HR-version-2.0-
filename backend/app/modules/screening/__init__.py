"""Domain Module: Screening (Step 3.10 Foundational Skill Registry).

Explainable matching engine, pgvector embedding comparisons, and deterministic skill registry.
"""

from app.modules.screening.skills import (
    RAW_TAXONOMY,
    TAXONOMY_SOURCE_PROVENANCE,
    TAXONOMY_VERSION,
    CollisionReportDTO,
    ExactMatcher,
    SkillDefinitionDTO,
    SkillExtractionResultDTO,
    SkillMatchResultDTO,
    SkillRegistry,
    TaxonomyMetadataDTO,
    TextNormalizer,
    exact_matcher,
    skill_registry,
    text_normalizer,
)

__all__ = [
    "RAW_TAXONOMY",
    "TAXONOMY_SOURCE_PROVENANCE",
    "TAXONOMY_VERSION",
    "CollisionReportDTO",
    "ExactMatcher",
    "SkillDefinitionDTO",
    "SkillExtractionResultDTO",
    "SkillMatchResultDTO",
    "SkillRegistry",
    "TaxonomyMetadataDTO",
    "TextNormalizer",
    "exact_matcher",
    "skill_registry",
    "text_normalizer",
]
