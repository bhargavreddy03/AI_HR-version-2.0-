"""Foundational Skill Registry: Thread-safe canonical mapping and collision detection.

Implements the single source of truth for technical competencies conforming to Step 3.10.
"""

from __future__ import annotations

import logging
import re
from typing import Final

from app.modules.screening.skills.normalizer import TextNormalizer, text_normalizer
from app.modules.screening.skills.schemas import (
    CollisionReportDTO,
    SkillDefinitionDTO,
    TaxonomyMetadataDTO,
    TaxonomySummaryReportDTO,
)
from app.modules.screening.skills.taxonomy import (
    RAW_TAXONOMY,
    TAXONOMY_SOURCE_PROVENANCE,
    TAXONOMY_VERSION,
)

logger = logging.getLogger(__name__)

# Sensitive demographic terms that must NEVER be introduced into the technical skill registry
PROHIBITED_DEMOGRAPHIC_TERMS: Final[frozenset[str]] = frozenset(
    {
        "male",
        "female",
        "gender",
        "age",
        "race",
        "ethnicity",
        "religion",
        "marital_status",
        "nationality",
        "sexual_orientation",
        "pregnancy",
    }
)


def generate_skill_id(canonical_name: str) -> str:
    """Derive a stable, URL-safe canonical skill identifier.

    Examples:
    - 'C++' -> 'cpp'
    - 'C#' -> 'csharp'
    - 'Node.js' -> 'nodejs'
    - '.NET' -> 'dotnet'
    - 'Data Structures and Algorithms' -> 'data_structures_and_algorithms'
    """
    special_mappings: dict[str, str] = {
        "c++": "cpp",
        "c#": "csharp",
        ".net": "dotnet",
        "asp.net": "asp_net",
        "vue.js": "vuejs",
        "node.js": "nodejs",
        "react.js": "reactjs",
        "next.js": "nextjs",
        "ci/cd": "ci_cd",
        "tcp/ip": "tcp_ip",
        "pl/sql": "pl_sql",
        "t-sql": "t_sql",
        "r": "r_lang",
        "c": "c_lang",
    }
    lowered = canonical_name.strip().lower()
    if lowered in special_mappings:
        return special_mappings[lowered]

    clean = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return clean or "unnamed_skill"


class SkillRegistry:
    """Thread-safe, code-backed registry of verified technical skills and canonical aliases.

    Guarantees:
    - O(1) canonical resolution for exact names and aliases.
    - Zero tolerance for demographic or protected characteristic attributes.
    - Deterministic collision logging: aliases conflicting across canonical skills are recorded.
    """

    def __init__(
        self,
        taxonomy: dict[str, dict[str, list[str]]] | None = None,
        normalizer: TextNormalizer | None = None,
    ) -> None:
        self._normalizer = normalizer or text_normalizer
        self._taxonomy_source = taxonomy or RAW_TAXONOMY

        # Primary registry data structures
        self._definitions_by_id: dict[str, SkillDefinitionDTO] = {}
        self._id_by_canonical_lower: dict[str, str] = {}
        self._id_by_normalized_alias: dict[str, str] = {}
        self._category_by_id: dict[str, str] = {}

        # Collision audit tracking
        self._collision_reports: list[CollisionReportDTO] = []

        # Build in-memory index
        self._build_index()

    def _build_index(self) -> None:
        """Construct deterministic lookup tables and detect any alias collisions."""
        alias_claimants: dict[str, list[str]] = {}

        for category, skills in self._taxonomy_source.items():
            for canonical_name, aliases in skills.items():
                # Governance check: ensure no sensitive attributes
                canon_clean = canonical_name.strip().lower()
                if canon_clean in PROHIBITED_DEMOGRAPHIC_TERMS:
                    raise ValueError(
                        f"Prohibited demographic term '{canonical_name}' detected in skill taxonomy"
                    )

                skill_id = generate_skill_id(canonical_name)
                definition = SkillDefinitionDTO(
                    skill_id=skill_id,
                    canonical_name=canonical_name,
                    category=category,
                    aliases=list(aliases),
                )

                self._definitions_by_id[skill_id] = definition
                self._id_by_canonical_lower[canon_clean] = skill_id
                self._category_by_id[skill_id] = category

                # Track claimants for canonical name as an alias
                normalized_canon = self._normalizer.normalize(canonical_name)
                alias_claimants.setdefault(normalized_canon, []).append(canonical_name)

                # Process all explicit aliases
                for raw_alias in aliases:
                    alias_clean = raw_alias.strip().lower()
                    if alias_clean in PROHIBITED_DEMOGRAPHIC_TERMS:
                        raise ValueError(
                            f"Prohibited demographic term '{raw_alias}' in aliases for '{canonical_name}'"
                        )
                    normalized_alias = self._normalizer.normalize(raw_alias)
                    if normalized_alias:
                        alias_claimants.setdefault(normalized_alias, []).append(canonical_name)

        # Index aliases and record any collisions
        for normalized_term, claimants in alias_claimants.items():
            unique_claimants = list(dict.fromkeys(claimants))
            primary_claimant = unique_claimants[0]
            primary_id = self._id_by_canonical_lower[primary_claimant.lower()]
            self._id_by_normalized_alias[normalized_term] = primary_id

            if len(unique_claimants) > 1:
                # Collision detected between distinct canonical skills
                collision = CollisionReportDTO(
                    alias=normalized_term,
                    primary_canonical=primary_claimant,
                    conflicting_canonicals=unique_claimants,
                    resolution_strategy="first_registered",
                )
                self._collision_reports.append(collision)
                logger.warning(
                    "Taxonomy collision on term '%s': mapped to '%s' (conflicting: %s)",
                    normalized_term,
                    primary_claimant,
                    unique_claimants,
                )

    def resolve(self, term: str) -> SkillDefinitionDTO | None:
        """Resolve a raw token or phrase to its canonical SkillDefinitionDTO, or None if unknown."""
        if not term:
            return None

        # 1. Direct lowercase canonical lookup
        lowered = term.strip().lower()
        if lowered in self._id_by_canonical_lower:
            skill_id = self._id_by_canonical_lower[lowered]
            return self._definitions_by_id[skill_id]

        # 2. Normalized alias lookup
        normalized = self._normalizer.normalize(term)
        if normalized in self._id_by_normalized_alias:
            skill_id = self._id_by_normalized_alias[normalized]
            return self._definitions_by_id[skill_id]

        return None

    def get_by_id(self, skill_id: str) -> SkillDefinitionDTO | None:
        """Retrieve canonical skill definition by stable identifier."""
        return self._definitions_by_id.get(skill_id)

    def all_definitions(self) -> list[SkillDefinitionDTO]:
        """Return all registered canonical skill definitions."""
        return list(self._definitions_by_id.values())

    def all_categories(self) -> list[str]:
        """Return unique list of registered categories."""
        return list(dict.fromkeys(self._category_by_id.values()))

    def get_collision_reports(self) -> list[CollisionReportDTO]:
        """Return auditable collision reports generated during taxonomy initialization."""
        return list(self._collision_reports)

    def lookup(self, term: str) -> SkillDefinitionDTO | None:
        """Alias for resolve() conforming to lookup interface."""
        return self.resolve(term)

    @property
    def metadata(self) -> TaxonomyMetadataDTO:
        """Access taxonomy metadata DTO."""
        return self.get_metadata()

    def get_collision_report(self) -> TaxonomySummaryReportDTO:
        """Return aggregate summary report of detected alias collisions."""
        return TaxonomySummaryReportDTO(
            total_collisions=len(self._collision_reports),
            collision_details=list(self._collision_reports),
        )

    def get_metadata(self) -> TaxonomyMetadataDTO:
        """Return official taxonomy metadata and governance statistics."""
        categories = self.all_categories()
        return TaxonomyMetadataDTO(
            version=TAXONOMY_VERSION,
            source_provenance=TAXONOMY_SOURCE_PROVENANCE,
            total_categories=len(categories),
            total_canonical_skills=len(self._definitions_by_id),
            total_indexed_aliases=len(self._id_by_normalized_alias),
            detected_collisions_count=len(self._collision_reports),
            category_list=categories,
        )


# Global singleton instance
skill_registry = SkillRegistry()
