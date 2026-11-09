"""Foundational Skill Registry and Deterministic Normalization Package."""

from app.modules.screening.skills.matcher import ExactMatcher, exact_matcher
from app.modules.screening.skills.normalizer import TextNormalizer, text_normalizer
from app.modules.screening.skills.registry import SkillRegistry, skill_registry
from app.modules.screening.skills.schemas import (
    CollisionReportDTO,
    SkillDefinitionDTO,
    SkillExtractionResultDTO,
    SkillMatchResultDTO,
    TaxonomyMetadataDTO,
)
from app.modules.screening.skills.taxonomy import (
    RAW_TAXONOMY,
    TAXONOMY_SOURCE_PROVENANCE,
    TAXONOMY_VERSION,
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
