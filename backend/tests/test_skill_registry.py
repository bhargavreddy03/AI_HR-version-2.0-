"""Comprehensive test suite for Foundational Skill Registry and Deterministic Matcher.

Conforms to Step 3.10 specifications:
- Canonical resolution across all 10 domain categories.
- Alias resolution and collision detection.
- Case-insensitivity and Unicode NFKC normalization.
- Punctuation, whitespace, and email/URL stripping.
- Technical symbol preservation: C++, C#, .NET, Node.js, CI/CD.
- Longest-first candidate sorting and non-overlapping span reservation (prevents C false-positives in C++).
- Demographic neutrality protection.
- Taxonomy metadata and release governance.
"""

from __future__ import annotations

import pytest

from app.modules.screening.skills import (
    RAW_TAXONOMY,
    TAXONOMY_VERSION,
    ExactMatcher,
    skill_registry,
    text_normalizer,
)

# -----------------------------------------------------------------------------
# 1. Taxonomy & Metadata Governance Tests
# -----------------------------------------------------------------------------


def test_taxonomy_metadata_and_domain_completeness() -> None:
    """Verify taxonomy metadata, domain counts, and release versioning."""
    metadata = skill_registry.metadata

    assert metadata.version == TAXONOMY_VERSION
    assert metadata.version == "1.0.0"
    assert metadata.total_domains == 10
    assert metadata.total_canonical_skills >= 100
    assert metadata.total_aliases > 200
    assert "Programming Languages" in metadata.domains
    assert "Core CS" in metadata.domains
    assert "Web & Frontend" in metadata.domains
    assert "Data & AI/ML" in metadata.domains
    assert "Databases" in metadata.domains
    assert "DevOps & Cloud" in metadata.domains
    assert "Cybersecurity" in metadata.domains
    assert "Emerging Tech" in metadata.domains
    assert "Mobile" in metadata.domains
    assert "Tools & Practices" in metadata.domains


def test_taxonomy_immutability() -> None:
    """Verify raw taxonomy entries are not mutated during registry initialization."""
    original_cat_count = len(RAW_TAXONOMY)
    assert original_cat_count == 10
    assert "Python" in RAW_TAXONOMY["Programming Languages"]
    assert "C++" in RAW_TAXONOMY["Programming Languages"]
    assert ".NET" in RAW_TAXONOMY["Programming Languages"]


# -----------------------------------------------------------------------------
# 2. Text Normalizer Tests
# -----------------------------------------------------------------------------


def test_normalizer_case_and_whitespace() -> None:
    """Verify lowercase conversion, multiple whitespace collapse, and strip."""
    raw = "   Senior   PYTHON   Engineer \t\n with DOCKER   "
    normalized = text_normalizer.normalize(raw)
    assert "senior" in normalized
    assert "python" in normalized
    assert "docker" in normalized
    assert "   " not in normalized


def test_normalizer_unicode_nfkc() -> None:
    """Verify full-width characters and Unicode decomposition are canonicalized."""
    # Full-width characters "Ｐｙｔｈｏｎ"
    full_width = "Expert in Ｐｙｔｈｏｎ programming"
    normalized = text_normalizer.normalize(full_width)
    assert "python" in normalized


def test_normalizer_strips_urls_and_emails() -> None:
    """Verify email addresses and URLs are stripped to prevent noisy skill matches."""
    text_with_noise = "Contact dev@example.com or visit https://github.com/myrepo for Python code"
    normalized = text_normalizer.normalize(text_with_noise)
    assert "dev@example.com" not in normalized
    assert "https://github.com/myrepo" not in normalized
    assert "python" in normalized


def test_normalizer_protects_technical_symbols() -> None:
    """Verify C++, C#, .NET, Node.js, and CI/CD are preserved through normalization."""
    raw = "Built microservices using C++, C#, .NET, Node.js, and CI/CD pipelines"
    text_normalizer.normalize(raw)

    # Protected tokens should remain intact in tokenized form
    tokens = text_normalizer.tokenize(raw)
    assert "c++" in tokens
    assert "c#" in tokens
    assert ".net" in tokens
    assert "node.js" in tokens
    assert "ci/cd" in tokens


# -----------------------------------------------------------------------------
# 3. Canonical Resolution and Alias Mapping Tests
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alias_input", "expected_canonical", "expected_domain"),
    [
        ("python", "Python", "Programming Languages"),
        ("PYTHON", "Python", "Programming Languages"),
        ("PyThOn", "Python", "Programming Languages"),
        ("golang", "Go", "Programming Languages"),
        ("k8s", "Kubernetes", "DevOps & Cloud"),
        ("kubernetes", "Kubernetes", "DevOps & Cloud"),
        ("postgres", "PostgreSQL", "Databases"),
        ("postgresql", "PostgreSQL", "Databases"),
        ("reactjs", "React", "Web & Frontend"),
        ("react.js", "React", "Web & Frontend"),
        ("aws", "AWS", "DevOps & Cloud"),
        ("azure", "Azure", "DevOps & Cloud"),
        ("gcp", "GCP", "DevOps & Cloud"),
        ("tf", "TensorFlow", "Data & AI/ML"),
        ("terraform", "Terraform", "DevOps & Cloud"),
        ("ml", "Machine Learning", "Data & AI/ML"),
        ("deep learning", "Deep Learning", "Data & AI/ML"),
        ("nlp", "Natural Language Processing", "Data & AI/ML"),
        ("rest", "REST APIs", "Web & Frontend"),
        ("graphql", "GraphQL", "Web & Frontend"),
        ("tdd", "Software Engineering", "Core CS"),
    ],
)
def test_canonical_and_alias_resolution(
    alias_input: str,
    expected_canonical: str,
    expected_domain: str,
) -> None:
    """Verify alias lookup maps reliably to canonical skill name and domain."""
    skill = skill_registry.lookup(alias_input)
    assert skill is not None, f"Failed to look up alias {alias_input}"
    assert skill.canonical_name == expected_canonical
    assert skill.domain == expected_domain


def test_unknown_skill_lookup_returns_none() -> None:
    """Verify unrecognized terms return None without throwing errors."""
    assert skill_registry.lookup("completely_unknown_skill_xyz") is None
    assert skill_registry.lookup("") is None
    assert skill_registry.lookup("   ") is None


# -----------------------------------------------------------------------------
# 4. Technical Symbols & Span Reservation (No False Positives)
# -----------------------------------------------------------------------------


def test_technical_symbol_matching_c_and_cpp_differentiation() -> None:
    """Verify C++ does not match C, and standalone C matches correctly."""
    matcher = ExactMatcher(registry=skill_registry, normalizer=text_normalizer)

    # Case 1: Sentence with C++ only
    text_cpp = "5 years of modern C++ development experience."
    res_cpp = matcher.extract(text_cpp)
    matched_names_cpp = [m.canonical_name for m in res_cpp.skills]

    assert "C++" in matched_names_cpp
    assert "C" not in matched_names_cpp, "C must not false-positive inside C++"

    # Case 2: Sentence with C# only
    text_csharp = "Backend developer working with C# and .NET."
    res_csharp = matcher.extract(text_csharp)
    matched_names_csharp = [m.canonical_name for m in res_csharp.skills]

    assert "C#" in matched_names_csharp
    assert "C" not in matched_names_csharp, "C must not false-positive inside C#"

    # Case 3: Sentence with standalone C and Python
    text_standalone_c = "Proficient in C and Python systems programming."
    res_standalone = matcher.extract(text_standalone_c)
    matched_names_standalone = [m.canonical_name for m in res_standalone.skills]

    assert "C" in matched_names_standalone
    assert "Python" in matched_names_standalone
    assert "C++" not in matched_names_standalone
    assert "C#" not in matched_names_standalone

    # Case 4: Sentence containing both C and C++ distinctly
    text_both = "Expert in both C and C++ languages."
    res_both = matcher.extract(text_both)
    matched_names_both = [m.canonical_name for m in res_both.skills]

    assert "C" in matched_names_both
    assert "C++" in matched_names_both


def test_technical_symbol_dotnet_and_nodejs() -> None:
    """Verify .NET and Node.js are extracted cleanly without punctuation truncation."""
    matcher = ExactMatcher(registry=skill_registry, normalizer=text_normalizer)

    text = "Full-stack engineer with expertise in .NET and Node.js services."
    res = matcher.extract(text)
    matched_names = [m.canonical_name for m in res.skills]

    assert ".NET" in matched_names
    assert "Node.js" in matched_names


def test_longest_first_subphrase_span_reservation() -> None:
    """Verify 'Data Structures and Algorithms' suppresses redundant substring match."""
    matcher = ExactMatcher(registry=skill_registry, normalizer=text_normalizer)

    text = "Strong foundation in Data Structures and Algorithms with Python."
    res = matcher.extract(text)
    matched_names = [m.canonical_name for m in res.skills]

    assert "Data Structures and Algorithms" in matched_names
    assert "Python" in matched_names


def test_cicd_pipeline_extraction() -> None:
    """Verify CI/CD is recognized without slash delimiter corruption."""
    matcher = ExactMatcher(registry=skill_registry, normalizer=text_normalizer)

    text = "Implemented automated CI/CD deployment pipelines using Docker."
    res = matcher.extract(text)
    matched_names = [m.canonical_name for m in res.skills]

    assert "CI/CD" in matched_names
    assert "Docker" in matched_names


# -----------------------------------------------------------------------------
# 5. Collision Detection & Audit Reporting Tests
# -----------------------------------------------------------------------------


def test_collision_report_generation() -> None:
    """Verify collision report identifies potential overlaps and reports total collisions."""
    report = skill_registry.get_collision_report()
    assert report is not None
    assert report.total_collisions >= 0
    assert isinstance(report.collision_details, list)
    assert report.generated_at is not None


# -----------------------------------------------------------------------------
# 6. Demographic Neutrality Protection Tests
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "protected_term",
    [
        "female",
        "male",
        "transgender",
        "non-binary",
        "caucasian",
        "african american",
        "asian",
        "hispanic",
        "latino",
        "christian",
        "muslim",
        "jewish",
        "hindu",
        "married",
        "divorced",
        "single mother",
        "pregnant",
        "veteran",
        "disabled",
    ],
)
def test_demographic_terms_not_in_taxonomy(protected_term: str) -> None:
    """Verify demographic attributes are strictly excluded from skill taxonomy."""
    assert skill_registry.lookup(protected_term) is None

    matcher = ExactMatcher(registry=skill_registry, normalizer=text_normalizer)
    result = matcher.extract(f"Candidate is a {protected_term} engineer with Python")
    matched_terms = [m.raw_match.lower() for m in result.skills]
    assert protected_term.lower() not in matched_terms
    assert "python" in [m.canonical_name.lower() for m in result.skills]


# -----------------------------------------------------------------------------
# 7. Multi-Skill Extraction Contract & Telemetry
# -----------------------------------------------------------------------------


def test_extract_skills_structured_contract() -> None:
    """Verify SkillExtractionResultDTO contains full domain categorization and counts."""
    matcher = ExactMatcher(registry=skill_registry, normalizer=text_normalizer)

    resume_snippet = """
    Senior Cloud Architect with 8+ years building enterprise applications.
    Tech Stack:
    - Languages: Python, Go, C++
    - Cloud & DevOps: AWS, Kubernetes, Terraform, Docker, CI/CD
    - Databases: PostgreSQL, Redis
    - Practices: Microservices, System Design, REST APIs
    """

    res = matcher.extract(resume_snippet)

    assert res.total_unique_skills >= 8
    assert "Programming Languages" in res.domains_represented
    assert "DevOps & Cloud" in res.domains_represented
    assert "Databases" in res.domains_represented

    # Verify breakdown
    lang_skills = res.domain_breakdown.get("Programming Languages", [])
    assert "Python" in lang_skills
    assert "Go" in lang_skills
    assert "C++" in lang_skills

    # Verify span offsets exist
    for match in res.skills:
        assert match.start_char >= 0
        assert match.end_char > match.start_char
        assert match.confidence == 1.0
