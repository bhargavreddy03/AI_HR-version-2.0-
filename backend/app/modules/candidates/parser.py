"""Resume Parser and OpenXML DOCX Extractor for Step 4.1.4.

Integrates with CanonicalSkillRegistry and SkillMatcherService to extract
structured candidate fields (Name, Email, Phone, Summary, Skills, Experience,
Education, Certifications, Projects).
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Final

import defusedxml.ElementTree as ET
from pydantic import BaseModel, Field

from app.core.errors import AppException
from app.modules.screening.skills.matcher import ExactMatcher, exact_matcher

logger = logging.getLogger(__name__)

# Regular expressions for contact info extraction
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", re.IGNORECASE
)
PHONE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)

# Section detection keywords
SECTION_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "summary": ("summary", "professional summary", "profile", "about me", "objective", "overview"),
    "skills": ("skills", "technical skills", "technologies", "competencies", "core skills", "proficiencies"),
    "experience": ("experience", "work experience", "employment history", "professional experience", "work history"),
    "education": ("education", "academic background", "academic history", "education and training"),
    "certifications": ("certifications", "certificates", "licenses", "credentials"),
    "projects": ("projects", "personal projects", "key projects", "selected projects", "portfolio"),
}


class DocxExtractorService:
    """Safe OpenXML DOCX text extraction using zipfile and defusedxml."""

    EXTRACTION_METHOD: Final[str] = "openxml_defusedxml_v1"
    EXTRACTION_VERSION: Final[str] = "1.0.0"

    def extract_from_bytes(self, file_bytes: bytes) -> str:
        """Extract all text paragraphs from raw DOCX bytes safely."""
        if not file_bytes:
            raise AppException("Cannot extract text from empty document bytes", status_code=422)

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                if "word/document.xml" not in zf.namelist():
                    raise AppException("Invalid DOCX: Missing word/document.xml", status_code=422)
                xml_content = zf.read("word/document.xml")
                root = ET.fromstring(xml_content)

                paragraphs: list[str] = []
                for p in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                    texts = [
                        node.text
                        for node in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                        if node.text
                    ]
                    if texts:
                        line = "".join(texts).strip()
                        if line:
                            paragraphs.append(line)
                return "\n".join(paragraphs)
        except zipfile.BadZipFile as exc:
            raise AppException("Malformed or corrupted DOCX archive", status_code=422) from exc
        except Exception as exc:
            logger.error("Unexpected error during DOCX extraction: %s", exc)
            raise AppException(f"Failed to extract text from DOCX: {exc}", status_code=422) from exc


docx_extractor_service = DocxExtractorService()


class ExtractedSectionItem(BaseModel):
    title: str
    organization: str | None = None
    date_range: str | None = None
    description: str | None = None


class ExtractedProfileData(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[ExtractedSectionItem] = Field(default_factory=list)
    education: list[ExtractedSectionItem] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[ExtractedSectionItem] = Field(default_factory=list)


def parse_resume_text(
    text: str,
    matcher: ExactMatcher | None = None,
) -> ExtractedProfileData:
    """Parse raw resume text into structured profile candidate fields."""
    if not text or not text.strip():
        return ExtractedProfileData()

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 1. Contact information
    email_match = EMAIL_PATTERN.search(text)
    email = email_match.group(0) if email_match else None

    phone_match = PHONE_PATTERN.search(text)
    phone = phone_match.group(0) if phone_match else None

    # 2. Candidate name heuristic: inspect first 3 non-empty lines
    name: str | None = None
    for line in lines[:3]:
        # Exclude line if it looks like email, phone, URL, or section header
        if EMAIL_PATTERN.search(line) or PHONE_PATTERN.search(line) or "http" in line.lower():
            continue
        lower_line = line.lower().strip(":# ")
        is_header = any(lower_line == k or lower_line.startswith(k) for kw in SECTION_KEYWORDS.values() for k in kw)
        if not is_header and 2 <= len(line.split()) <= 4 and len(line) <= 50:
            name = line.strip()
            break

    # 3. Section segmentation
    sections: dict[str, list[str]] = {
        "summary": [],
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
    }
    current_section: str | None = None

    for line in lines:
        lower_line = line.lower().strip(":#*_- ")
        detected_section = None
        for sec_name, keywords in SECTION_KEYWORDS.items():
            if lower_line in keywords or any(lower_line == kw or lower_line.startswith(f"{kw}:") for kw in keywords):
                detected_section = sec_name
                break

        if detected_section:
            current_section = detected_section
            continue

        if current_section:
            sections[current_section].append(line)

    # Summary
    summary = " ".join(sections["summary"]) if sections["summary"] else None
    if summary and len(summary) > 1000:
        summary = summary[:1000] + "..."

    # Skills extraction (taxonomy-driven via SkillMatcherService)
    skills: list[str] = []
    if matcher:
        match_result = matcher.extract(text)
        skills = [m.canonical_name for m in match_result.extracted_skills]
    else:
        # Fallback to comma/bullet split from skills section
        for s_line in sections["skills"]:
            for part in re.split(r"[,;|•·\n]", s_line):
                cleaned = part.strip()
                if cleaned and len(cleaned) <= 40 and cleaned not in skills:
                    skills.append(cleaned)

    # Experience entries
    experience_items: list[ExtractedSectionItem] = []
    current_exp_lines: list[str] = []
    for line in sections["experience"]:
        # If line contains year range or bullet, treat as entry separator
        if re.search(r"\b(20\d\d|19\d\d)\b", line) and len(current_exp_lines) > 0:
            exp_item = _build_experience_item(current_exp_lines)
            if exp_item:
                experience_items.append(exp_item)
            current_exp_lines = [line]
        else:
            current_exp_lines.append(line)
    if current_exp_lines:
        exp_item = _build_experience_item(current_exp_lines)
        if exp_item:
            experience_items.append(exp_item)

    # Education entries
    education_items: list[ExtractedSectionItem] = []
    current_edu_lines: list[str] = []
    for line in sections["education"]:
        if re.search(r"\b(20\d\d|19\d\d)\b", line) and len(current_edu_lines) > 0:
            edu_item = _build_education_item(current_edu_lines)
            if edu_item:
                education_items.append(edu_item)
            current_edu_lines = [line]
        else:
            current_edu_lines.append(line)
    if current_edu_lines:
        edu_item = _build_education_item(current_edu_lines)
        if edu_item:
            education_items.append(edu_item)

    # Certifications
    certifications: list[str] = []
    for line in sections["certifications"]:
        cleaned = line.lstrip("•*- ").strip()
        if cleaned and len(cleaned) <= 120 and cleaned not in certifications:
            certifications.append(cleaned)

    # Projects
    project_items: list[ExtractedSectionItem] = []
    current_proj_lines: list[str] = []
    for line in sections["projects"]:
        if line.startswith(("#", "**", "Project:", "•")) and len(current_proj_lines) > 0:
            p_item = _build_project_item(current_proj_lines)
            if p_item:
                project_items.append(p_item)
            current_proj_lines = [line]
        else:
            current_proj_lines.append(line)
    if current_proj_lines:
        p_item = _build_project_item(current_proj_lines)
        if p_item:
            project_items.append(p_item)

    return ExtractedProfileData(
        name=name,
        email=email,
        phone=phone,
        summary=summary,
        skills=skills,
        experience=experience_items,
        education=education_items,
        certifications=certifications,
        projects=project_items,
    )


def _build_experience_item(lines: list[str]) -> ExtractedSectionItem | None:
    if not lines:
        return None
    header = lines[0]
    date_match = re.search(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|[0-9]{1,2}/)?\s*(?:19|20)\d\d\s*[-–to]+\s*(?:Present|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|[0-9]{1,2}/)?\s*(?:19|20)\d\d))", header, re.IGNORECASE)
    date_range = date_match.group(0) if date_match else None

    # Title and Organization
    parts = re.split(r"[-–|@,]", header)
    title = parts[0].strip()
    org = parts[1].strip() if len(parts) > 1 else None
    desc = " ".join(lines[1:]).strip() if len(lines) > 1 else None

    return ExtractedSectionItem(
        title=title or "Software Professional",
        organization=org,
        date_range=date_range,
        description=desc,
    )


def _build_education_item(lines: list[str]) -> ExtractedSectionItem | None:
    if not lines:
        return None
    header = lines[0]
    date_match = re.search(r"\b((?:19|20)\d\d(?:\s*[-–]\s*(?:19|20)\d\d)?)\b", header)
    date_range = date_match.group(0) if date_match else None

    parts = re.split(r"[-–|,]", header)
    degree = parts[0].strip()
    institution = parts[1].strip() if len(parts) > 1 else None

    return ExtractedSectionItem(
        title=degree or "Degree / Qualification",
        organization=institution,
        date_range=date_range,
        description=" ".join(lines[1:]).strip() if len(lines) > 1 else None,
    )


def _build_project_item(lines: list[str]) -> ExtractedSectionItem | None:
    if not lines:
        return None
    title = lines[0].lstrip("#*•- ").strip()
    desc = " ".join(lines[1:]).strip() if len(lines) > 1 else None
    return ExtractedSectionItem(
        title=title or "Project",
        description=desc,
    )
