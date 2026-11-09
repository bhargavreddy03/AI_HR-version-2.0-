"""Deterministic Text Normalizer for Technical Skill Extraction.

Preserves domain-critical symbols (C++, C#, .NET, CI/CD, Node.js) while normalizing whitespace,
Unicode diacritics, URLs, and punctuation conforming to Step 3.10 requirements.
"""

from __future__ import annotations

import re
import unicodedata


class TextNormalizer:
    """Cleans and standardizes raw text prior to deterministic skill matching.

    Guarantees:
    - Special technical expressions (C++, C#, .NET, CI/CD, Node.js, etc.) are protected.
    - Uses purely alphabetic placeholder tokens (XTECH...X) to prevent accidental punctuation stripping.
    - Deterministic, idempotent normalization: normalize(normalize(t)) == normalize(t).
    """

    # Protected technical expressions mapped to purely alphabetic placeholders
    _PROTECTED_TOKENS: dict[str, str] = {
        "c++": "XTECHCPPX",
        "c#": "XTECHCSHARPX",
        "c/c++": "XTECHCCPPX",
        ".net": "XTECHDOTNETX",
        "f#": "XTECHFSHARPX",
        "node.js": "XTECHNODEJSX",
        "ci/cd": "XTECHCICDX",
        "vue.js": "XTECHVUEJSX",
        "react.js": "XTECHREACTJSX",
        "next.js": "XTECHNEXTJSX",
        "tcp/ip": "XTECHTCPIPX",
        "pl/sql": "XTECHPLSQLX",
        "t-sql": "XTECHTSQLX",
    }
    _REVERSE_PROTECTED: dict[str, str] = {v: k for k, v in _PROTECTED_TOKENS.items()}

    def normalize(self, text: str | None) -> str:
        """Execute deterministic cleaning and canonical normalization pipeline."""
        if not text:
            return ""

        # 1. Unicode NFKC normalization
        normalized = unicodedata.normalize("NFKC", text)

        # 2. Lowercase conversion for case-insensitive matching
        lowered = normalized.lower()

        # 3. Protect technical expressions with purely alphabetic placeholders
        for token, placeholder in self._PROTECTED_TOKENS.items():
            lowered = lowered.replace(token, placeholder.lower())

        # 4. Remove URLs and web protocols
        cleaned = re.sub(r"https?://\S+|www\.\S+", " ", lowered)

        # 5. Remove email addresses
        cleaned = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", " ", cleaned)

        # 6. Normalize common list separators (bullet points, pipes, slashes, brackets)
        cleaned = re.sub(r"[•·\|\(\)\[\]\{\}\*]", " ", cleaned)

        # 7. Remove English possessives ('s and s')
        cleaned = re.sub(r"'s\b|\b's", "", cleaned)

        # 8. Normalize miscellaneous punctuation except word hyphens and letters
        cleaned = re.sub(r"[,;:\?!\"'`~^<>=_/]", " ", cleaned)

        # 9. Collapse multiple whitespace and strip
        collapsed = re.sub(r"\s+", " ", cleaned).strip()

        # 10. Restore protected tokens
        for placeholder, token in self._REVERSE_PROTECTED.items():
            collapsed = collapsed.replace(placeholder.lower(), token)

        return collapsed

    def tokenize(self, text: str | None) -> list[str]:
        """Tokenize normalized text into clean tokens preserving technical symbols."""
        norm = self.normalize(text)
        return norm.split() if norm else []



# Global singleton instance
text_normalizer = TextNormalizer()
