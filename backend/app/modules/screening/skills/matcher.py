"""Deterministic Exact and Phrase Matcher for Skill Extraction.

Uses pre-compiled regex patterns sorted longest-first with span-based collision prevention
to prevent substring false positives (e.g. 'C' matching inside 'C++', or 'Algorithms'
matching inside 'Data Structures and Algorithms').
"""

from __future__ import annotations

import logging
import re

from app.modules.screening.skills.normalizer import TextNormalizer, text_normalizer
from app.modules.screening.skills.registry import SkillRegistry, skill_registry
from app.modules.screening.skills.schemas import (
    SkillExtractionResultDTO,
    SkillMatchResultDTO,
)

logger = logging.getLogger(__name__)


class ExactMatcher:
    """Scans normalized text for canonical skills and aliases using deterministic regex patterns.

    Ordering & Span Reservation:
    - Longest phrases are evaluated first.
    - Matched character spans are claimed; subsequent shorter candidates cannot overlap
      with already claimed spans. This cleanly prevents 'C' from matching inside 'C++' or 'C#',
      and prevents 'Algorithms' from matching inside 'Data Structures and Algorithms'.
    """

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        normalizer: TextNormalizer | None = None,
    ) -> None:
        self._registry = registry or skill_registry
        self._normalizer = normalizer or text_normalizer
        self._patterns: list[tuple[re.Pattern[str], str, str, bool]] = []
        self._build_patterns()

    def _build_patterns(self) -> None:
        """Compile regex patterns for every alias and canonical name, sorted longest first."""
        candidates: list[tuple[str, str, str, bool]] = []

        for definition in self._registry.all_definitions():
            # Canonical term
            norm_canon = self._normalizer.normalize(definition.canonical_name)
            if norm_canon:
                candidates.append((norm_canon, definition.canonical_name, definition.skill_id, True))

            # Aliases
            for alias in definition.aliases:
                norm_alias = self._normalizer.normalize(alias)
                if norm_alias and norm_alias != norm_canon:
                    candidates.append((norm_alias, definition.canonical_name, definition.skill_id, False))

        # Sort candidates by character length descending (longest first)
        candidates.sort(key=lambda item: len(item[0]), reverse=True)

        seen_terms: set[str] = set()
        for term, canonical_name, skill_id, is_canonical in candidates:
            if term in seen_terms:
                continue
            seen_terms.add(term)

            # Word boundary regex respecting special technical symbols
            escaped = re.escape(term)
            # Boundary before: not preceded by alphanumeric, underscore, or plus/hash if term is single letter
            # Boundary after: not followed by alphanumeric, underscore, or plus/hash
            pattern_str = rf"(?<![a-z0-9_\+#]){escaped}(?![a-z0-9_\+#])"
            compiled = re.compile(pattern_str, re.IGNORECASE)
            self._patterns.append((compiled, canonical_name, skill_id, is_canonical))

    def extract(self, raw_text: str | None) -> SkillExtractionResultDTO:
        """Execute deterministic exact matching against raw text and return structured extraction."""
        if not raw_text or not raw_text.strip():
            return SkillExtractionResultDTO(
                extracted_skills=[],
                total_matches=0,
                matched_categories=[],
                categorized_breakdown={},
            )

        normalized_text = self._normalizer.normalize(raw_text)
        claimed_spans: list[tuple[int, int]] = []
        matched_by_id: dict[str, SkillMatchResultDTO] = {}
        matched_categories_set: set[str] = set()
        categorized_breakdown: dict[str, list[str]] = {}

        for pattern, canonical_name, skill_id, is_canonical in self._patterns:
            # Check for matches across the entire text
            for match in pattern.finditer(normalized_text):
                start, end = match.span()

                # Check if this match overlaps with any previously claimed span (from longer candidate)
                overlaps = any(
                    max(start, c_start) < min(end, c_end)
                    for c_start, c_end in claimed_spans
                )
                if overlaps:
                    continue

                # Claim this span
                claimed_spans.append((start, end))

                # If this canonical skill was not already recorded, register it
                if skill_id not in matched_by_id:
                    definition = self._registry.get_by_id(skill_id)
                    category = definition.category if definition else "General"
                    result = SkillMatchResultDTO(
                        skill_id=skill_id,
                        canonical_name=canonical_name,
                        category=category,
                        matched_term=match.group(0),
                        is_exact_canonical=is_canonical,
                        start_char=start,
                        end_char=end,
                        confidence=1.0,
                    )
                    matched_by_id[skill_id] = result
                    matched_categories_set.add(category)
                    categorized_breakdown.setdefault(category, []).append(canonical_name)

        extracted_list = list(matched_by_id.values())
        return SkillExtractionResultDTO(
            extracted_skills=extracted_list,
            total_matches=len(extracted_list),
            matched_categories=sorted(matched_categories_set),
            categorized_breakdown=categorized_breakdown,
        )


# Global singleton instance
exact_matcher = ExactMatcher()
