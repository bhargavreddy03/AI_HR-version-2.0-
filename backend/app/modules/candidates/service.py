"""Candidate Service orchestrating global candidate profiles, resumes, skills, and preferences.

Conforms strictly to Step 4.1 Candidate Portal specifications.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    EntityNotFoundException,
    ValidationException,
)
from app.core.security.file_security import (
    MAX_FILE_SIZE_BYTES,
    check_dangerous_executables,
    generate_secure_storage_name,
    get_malware_scanner,
    sanitize_filename,
    validate_docx_content,
    validate_file_size,
    validate_pdf_content,
)
from app.modules.auth.models import CandidateUserProfile, User
from app.modules.candidates.models import (
    CandidateCertification,
    CandidateEducation,
    CandidateExperience,
    CandidateLanguage,
    CandidateNotification,
    CandidatePreference,
    CandidateProject,
    CandidateResume,
    CandidateResumeStatus,
)
from app.modules.candidates.parser import (
    DocxExtractorService,
    docx_extractor_service,
    parse_resume_text,
)
from app.modules.jobs.models import JobApplication
from app.modules.candidates.schemas import (
    CandidateNotificationRead,
    CandidateNotificationsResponse,
    CandidatePreferenceRead,
    CandidatePreferenceUpdate,
    CandidateProfileRead,
    CandidateProfileUpdate,
    CandidateResumeRead,
    CandidateSkillsResponse,
    CertificationCreate,
    CertificationRead,
    EducationCreate,
    EducationRead,
    EducationUpdate,
    ExperienceCreate,
    ExperienceRead,
    ExperienceUpdate,
    LanguageCreate,
    LanguageRead,
    ProjectCreate,
    ProjectRead,
    ResumeDownloadUrlResponse,
    ResumeExtractedDataUpdate,
    ResumeExtractionResponse,
    ResumeUploadResponse,
)
from app.modules.documents.extractor import PDFExtractorService, pdf_extractor_service
from app.modules.documents.storage import StorageService, storage_service
from app.modules.screening.skills.matcher import ExactMatcher, exact_matcher
from app.modules.screening.skills.registry import SkillRegistry, skill_registry

logger = logging.getLogger(__name__)


class CandidateService:
    """Domain service managing candidate profile lifecycle, resumes, and personal portfolio data."""

    def __init__(
        self,
        storage: StorageService | None = None,
        extractor: PDFExtractorService | None = None,
        matcher: ExactMatcher | None = None,
        registry: SkillRegistry | None = None,
        docx_extractor: DocxExtractorService | None = None,
    ) -> None:
        self._storage = storage or storage_service
        self._extractor = extractor or pdf_extractor_service
        self._matcher = matcher or exact_matcher
        self._registry = registry or skill_registry
        self._docx_extractor = docx_extractor or docx_extractor_service

    # -------------------------------------------------------------------------
    # Profile & Personal Information
    # -------------------------------------------------------------------------
    async def get_candidate_profile(self, db: AsyncSession, user_id: UUID) -> CandidateProfileRead:
        """Retrieve aggregated candidate profile with completion score."""
        user_res = await db.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        if not user:
            raise EntityNotFoundException("Candidate user account", user_id)

        profile_res = await db.execute(
            select(CandidateUserProfile).where(CandidateUserProfile.user_id == user_id)
        )
        profile = profile_res.scalar_one_or_none()

        # Fetch child collections
        exp_res = await db.execute(
            select(CandidateExperience)
            .where(CandidateExperience.user_id == user_id)
            .order_by(desc(CandidateExperience.created_at))
        )
        experiences = [ExperienceRead.model_validate(e) for e in exp_res.scalars().all()]

        edu_res = await db.execute(
            select(CandidateEducation)
            .where(CandidateEducation.user_id == user_id)
            .order_by(desc(CandidateEducation.created_at))
        )
        educations = [EducationRead.model_validate(e) for e in edu_res.scalars().all()]

        cert_res = await db.execute(
            select(CandidateCertification)
            .where(CandidateCertification.user_id == user_id)
            .order_by(desc(CandidateCertification.created_at))
        )
        certifications = [CertificationRead.model_validate(c) for c in cert_res.scalars().all()]

        proj_res = await db.execute(
            select(CandidateProject)
            .where(CandidateProject.user_id == user_id)
            .order_by(desc(CandidateProject.created_at))
        )
        projects = [ProjectRead.model_validate(p) for p in proj_res.scalars().all()]

        lang_res = await db.execute(
            select(CandidateLanguage)
            .where(CandidateLanguage.user_id == user_id)
            .order_by(desc(CandidateLanguage.created_at))
        )
        languages = [LanguageRead.model_validate(lang) for lang in lang_res.scalars().all()]

        pref_res = await db.execute(
            select(CandidatePreference).where(CandidatePreference.user_id == user_id)
        )
        pref_model = pref_res.scalar_one_or_none()
        preferences = CandidatePreferenceRead.model_validate(pref_model) if pref_model else None

        # Check default resume existence for completion metric
        resume_res = await db.execute(
            select(CandidateResume).where(CandidateResume.user_id == user_id).limit(1)
        )
        has_resume = resume_res.scalar_one_or_none() is not None

        # Compute profile completion percentage
        completion = 0
        if user.first_name and user.last_name and user.email:
            completion += 20
        if profile and (profile.headline or profile.bio):
            completion += 15
        if profile and len(profile.self_declared_skills) > 0:
            completion += 15
        if len(experiences) > 0:
            completion += 20
        if len(educations) > 0:
            completion += 15
        if has_resume:
            completion += 15

        completion = min(100, completion)

        raw_avatar = getattr(user, "avatar_url", None)
        avatar_val = raw_avatar if isinstance(raw_avatar, str) else None

        return CandidateProfileRead(
            user_id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            avatar_url=avatar_val,
            is_verified=bool(getattr(user, "is_verified", True)),
            headline=profile.headline if profile else None,
            bio=profile.bio if profile else None,
            phone=profile.phone if profile else user.phone_number,
            location_city=profile.location_city if profile else None,
            location_country=profile.location_country if profile else None,
            preferred_title=profile.preferred_title if profile else None,
            work_authorization=profile.work_authorization if profile else None,
            portfolio_urls=profile.portfolio_urls if profile else [],
            self_declared_skills=profile.self_declared_skills if profile else [],
            experiences=experiences,
            educations=educations,
            certifications=certifications,
            projects=projects,
            languages=languages,
            preferences=preferences,
            profile_completion_percentage=completion,
        )

    async def update_candidate_profile(
        self, db: AsyncSession, user_id: UUID, payload: CandidateProfileUpdate
    ) -> CandidateProfileRead:
        """Update core candidate profile information."""
        user_res = await db.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        if not user:
            raise EntityNotFoundException("Candidate user account", user_id)

        # Update user names if provided
        if payload.first_name is not None:
            user.first_name = payload.first_name.strip()
        if payload.last_name is not None:
            user.last_name = payload.last_name.strip()
        if payload.phone is not None:
            user.phone_number = payload.phone.strip()
        if payload.avatar_url is not None:
            user.avatar_url = payload.avatar_url.strip() if payload.avatar_url else None

        # Update or create CandidateUserProfile
        profile_res = await db.execute(
            select(CandidateUserProfile).where(CandidateUserProfile.user_id == user_id)
        )
        profile = profile_res.scalar_one_or_none()
        if not profile:
            profile = CandidateUserProfile(
                user_id=user_id,
                headline=payload.headline,
                bio=payload.bio,
                phone=payload.phone,
                location_city=payload.location_city,
                location_country=payload.location_country,
                preferred_title=payload.preferred_title,
                work_authorization=payload.work_authorization,
                portfolio_urls=payload.portfolio_urls or [],
                self_declared_skills=[],
            )
            db.add(profile)
        else:
            if payload.headline is not None:
                profile.headline = payload.headline.strip() if payload.headline else None
            if payload.bio is not None:
                profile.bio = payload.bio.strip() if payload.bio else None
            if payload.phone is not None:
                profile.phone = payload.phone.strip() if payload.phone else None
            if payload.location_city is not None:
                profile.location_city = (
                    payload.location_city.strip() if payload.location_city else None
                )
            if payload.location_country is not None:
                profile.location_country = (
                    payload.location_country.strip() if payload.location_country else None
                )
            if payload.preferred_title is not None:
                profile.preferred_title = (
                    payload.preferred_title.strip() if payload.preferred_title else None
                )
            if payload.work_authorization is not None:
                profile.work_authorization = (
                    payload.work_authorization.strip() if payload.work_authorization else None
                )
            if payload.portfolio_urls is not None:
                profile.portfolio_urls = payload.portfolio_urls

        await db.commit()
        return await self.get_candidate_profile(db, user_id)

    # -------------------------------------------------------------------------
    # Work Experience CRUD
    # -------------------------------------------------------------------------
    async def add_experience(
        self, db: AsyncSession, user_id: UUID, payload: ExperienceCreate
    ) -> ExperienceRead:
        """Add work experience entry to candidate profile."""
        now = utc_now()
        entry = CandidateExperience(
            id=generate_uuid7(),
            user_id=user_id,
            job_title=payload.job_title.strip(),
            company_name=payload.company_name.strip(),
            location=payload.location.strip() if payload.location else None,
            start_date=payload.start_date.strip(),
            end_date=payload.end_date.strip() if payload.end_date else None,
            is_current=payload.is_current,
            description=payload.description.strip() if payload.description else None,
            skills=payload.skills,
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return ExperienceRead.model_validate(entry)

    async def update_experience(
        self, db: AsyncSession, user_id: UUID, experience_id: UUID, payload: ExperienceUpdate
    ) -> ExperienceRead:
        """Update existing work experience entry."""
        res = await db.execute(
            select(CandidateExperience).where(
                CandidateExperience.id == experience_id,
                CandidateExperience.user_id == user_id,
            )
        )
        entry = res.scalar_one_or_none()
        if not entry:
            raise EntityNotFoundException("Experience entry", experience_id)

        if payload.job_title is not None:
            entry.job_title = payload.job_title.strip()
        if payload.company_name is not None:
            entry.company_name = payload.company_name.strip()
        if payload.location is not None:
            entry.location = payload.location.strip() if payload.location else None
        if payload.start_date is not None:
            entry.start_date = payload.start_date.strip()
        if payload.end_date is not None:
            entry.end_date = payload.end_date.strip() if payload.end_date else None
        if payload.is_current is not None:
            entry.is_current = payload.is_current
        if payload.description is not None:
            entry.description = payload.description.strip() if payload.description else None
        if payload.skills is not None:
            entry.skills = payload.skills

        await db.commit()
        await db.refresh(entry)
        return ExperienceRead.model_validate(entry)

    async def delete_experience(self, db: AsyncSession, user_id: UUID, experience_id: UUID) -> None:
        """Delete work experience entry with IDOR protection."""
        res = await db.execute(
            select(CandidateExperience).where(
                CandidateExperience.id == experience_id,
                CandidateExperience.user_id == user_id,
            )
        )
        entry = res.scalar_one_or_none()
        if not entry:
            raise EntityNotFoundException("Experience entry", experience_id)

        await db.delete(entry)
        await db.commit()

    # -------------------------------------------------------------------------
    # Education CRUD
    # -------------------------------------------------------------------------
    async def add_education(
        self, db: AsyncSession, user_id: UUID, payload: EducationCreate
    ) -> EducationRead:
        """Add education entry to candidate profile."""
        now = utc_now()
        entry = CandidateEducation(
            id=generate_uuid7(),
            user_id=user_id,
            institution=payload.institution.strip(),
            degree=payload.degree.strip(),
            field_of_study=payload.field_of_study.strip(),
            start_year=payload.start_year,
            end_year=payload.end_year,
            grade=payload.grade.strip() if payload.grade else None,
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return EducationRead.model_validate(entry)

    async def update_education(
        self, db: AsyncSession, user_id: UUID, education_id: UUID, payload: EducationUpdate
    ) -> EducationRead:
        """Update education entry with IDOR check."""
        res = await db.execute(
            select(CandidateEducation).where(
                CandidateEducation.id == education_id,
                CandidateEducation.user_id == user_id,
            )
        )
        entry = res.scalar_one_or_none()
        if not entry:
            raise EntityNotFoundException("Education entry", education_id)

        if payload.institution is not None:
            entry.institution = payload.institution.strip()
        if payload.degree is not None:
            entry.degree = payload.degree.strip()
        if payload.field_of_study is not None:
            entry.field_of_study = payload.field_of_study.strip()
        if payload.start_year is not None:
            entry.start_year = payload.start_year
        if payload.end_year is not None:
            entry.end_year = payload.end_year
        if payload.grade is not None:
            entry.grade = payload.grade.strip() if payload.grade else None

        await db.commit()
        await db.refresh(entry)
        return EducationRead.model_validate(entry)

    async def delete_education(self, db: AsyncSession, user_id: UUID, education_id: UUID) -> None:
        """Delete education entry."""
        res = await db.execute(
            select(CandidateEducation).where(
                CandidateEducation.id == education_id,
                CandidateEducation.user_id == user_id,
            )
        )
        entry = res.scalar_one_or_none()
        if not entry:
            raise EntityNotFoundException("Education entry", education_id)

        await db.delete(entry)
        await db.commit()

    # -------------------------------------------------------------------------
    # Certifications CRUD
    # -------------------------------------------------------------------------
    async def add_certification(
        self, db: AsyncSession, user_id: UUID, payload: CertificationCreate
    ) -> CertificationRead:
        now = utc_now()
        entry = CandidateCertification(
            id=generate_uuid7(),
            user_id=user_id,
            name=payload.name.strip(),
            issuing_organization=payload.issuing_organization.strip(),
            issue_date=payload.issue_date.strip() if payload.issue_date else None,
            expiration_date=payload.expiration_date.strip() if payload.expiration_date else None,
            credential_id=payload.credential_id.strip() if payload.credential_id else None,
            credential_url=payload.credential_url.strip() if payload.credential_url else None,
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return CertificationRead.model_validate(entry)

    async def delete_certification(self, db: AsyncSession, user_id: UUID, cert_id: UUID) -> None:
        res = await db.execute(
            select(CandidateCertification).where(
                CandidateCertification.id == cert_id,
                CandidateCertification.user_id == user_id,
            )
        )
        entry = res.scalar_one_or_none()
        if not entry:
            raise EntityNotFoundException("Certification", cert_id)
        await db.delete(entry)
        await db.commit()

    # -------------------------------------------------------------------------
    # Projects CRUD
    # -------------------------------------------------------------------------
    async def add_project(
        self, db: AsyncSession, user_id: UUID, payload: ProjectCreate
    ) -> ProjectRead:
        now = utc_now()
        entry = CandidateProject(
            id=generate_uuid7(),
            user_id=user_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            role=payload.role.strip() if payload.role else None,
            project_url=payload.project_url.strip() if payload.project_url else None,
            skills=payload.skills,
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return ProjectRead.model_validate(entry)

    async def delete_project(self, db: AsyncSession, user_id: UUID, project_id: UUID) -> None:
        res = await db.execute(
            select(CandidateProject).where(
                CandidateProject.id == project_id,
                CandidateProject.user_id == user_id,
            )
        )
        entry = res.scalar_one_or_none()
        if not entry:
            raise EntityNotFoundException("Project", project_id)
        await db.delete(entry)
        await db.commit()

    # -------------------------------------------------------------------------
    # Languages CRUD
    # -------------------------------------------------------------------------
    async def add_language(
        self, db: AsyncSession, user_id: UUID, payload: LanguageCreate
    ) -> LanguageRead:
        now = utc_now()
        entry = CandidateLanguage(
            id=generate_uuid7(),
            user_id=user_id,
            language=payload.language.strip(),
            proficiency=payload.proficiency.strip(),
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return LanguageRead.model_validate(entry)

    async def delete_language(self, db: AsyncSession, user_id: UUID, language_id: UUID) -> None:
        res = await db.execute(
            select(CandidateLanguage).where(
                CandidateLanguage.id == language_id,
                CandidateLanguage.user_id == user_id,
            )
        )
        entry = res.scalar_one_or_none()
        if not entry:
            raise EntityNotFoundException("Language entry", language_id)
        await db.delete(entry)
        await db.commit()

    # -------------------------------------------------------------------------
    # Skills Management (Integrated with Step 3.10 Normalizer)
    # -------------------------------------------------------------------------
    async def update_skills(
        self, db: AsyncSession, user_id: UUID, raw_skills: list[str]
    ) -> CandidateSkillsResponse:
        """Update candidate self-declared skills using canonical normalization."""
        profile_res = await db.execute(
            select(CandidateUserProfile).where(CandidateUserProfile.user_id == user_id)
        )
        profile = profile_res.scalar_one_or_none()
        if not profile:
            profile = CandidateUserProfile(
                user_id=user_id,
                portfolio_urls=[],
                self_declared_skills=[],
            )
            db.add(profile)

        # Resolve skills using canonical taxonomy registry
        normalized_list: list[str] = []
        for s in raw_skills:
            cleaned = s.strip()
            if not cleaned:
                continue
            skill_def = self._registry.resolve(cleaned)
            canonical = skill_def.canonical_name if skill_def else cleaned
            if canonical not in normalized_list:
                normalized_list.append(canonical)

        profile.self_declared_skills = normalized_list
        await db.commit()

        return CandidateSkillsResponse(
            skills=normalized_list,
            total_count=len(normalized_list),
            normalized_skills=normalized_list,
        )

    # -------------------------------------------------------------------------
    # Preferences Management
    # -------------------------------------------------------------------------
    async def get_preferences(self, db: AsyncSession, user_id: UUID) -> CandidatePreferenceRead:
        """Get candidate career preferences."""
        res = await db.execute(
            select(CandidatePreference).where(CandidatePreference.user_id == user_id)
        )
        pref = res.scalar_one_or_none()
        if not pref:
            pref = CandidatePreference(
                user_id=user_id,
                desired_job_titles=[],
                desired_locations=[],
                remote_preference="flexible",
                employment_types=["full_time"],
                minimum_salary=None,
                currency="USD",
            )
            db.add(pref)
            await db.commit()
            await db.refresh(pref)

        return CandidatePreferenceRead.model_validate(pref)

    async def update_preferences(
        self, db: AsyncSession, user_id: UUID, payload: CandidatePreferenceUpdate
    ) -> CandidatePreferenceRead:
        """Update candidate career preferences."""
        res = await db.execute(
            select(CandidatePreference).where(CandidatePreference.user_id == user_id)
        )
        pref = res.scalar_one_or_none()
        if not pref:
            pref = CandidatePreference(
                user_id=user_id,
                desired_job_titles=payload.desired_job_titles or [],
                desired_locations=payload.desired_locations or [],
                remote_preference=payload.remote_preference or "flexible",
                employment_types=payload.employment_types or ["full_time"],
                minimum_salary=payload.minimum_salary,
                currency=payload.currency or "USD",
            )
            db.add(pref)
        else:
            if payload.desired_job_titles is not None:
                pref.desired_job_titles = payload.desired_job_titles
            if payload.desired_locations is not None:
                pref.desired_locations = payload.desired_locations
            if payload.remote_preference is not None:
                pref.remote_preference = payload.remote_preference
            if payload.employment_types is not None:
                pref.employment_types = payload.employment_types
            if payload.minimum_salary is not None:
                pref.minimum_salary = payload.minimum_salary
            if payload.currency is not None:
                pref.currency = payload.currency

        await db.commit()
        await db.refresh(pref)
        return CandidatePreferenceRead.model_validate(pref)

    # -------------------------------------------------------------------------
    # Resume Management (Integrated with Step 3.10 Storage & Extraction)
    # -------------------------------------------------------------------------
    async def upload_resume(
        self, db: AsyncSession, user_id: UUID, file: UploadFile
    ) -> ResumeUploadResponse:
        """Process candidate resume upload (PDF/DOCX), enforce security bounds, compute SHA-256, store in S3, and extract text/skills."""
        raw_filename = file.filename or "resume.pdf"
        clean_filename = sanitize_filename(raw_filename)
        ext = clean_filename.rsplit(".", 1)[-1].lower() if "." in clean_filename else ""

        if ext not in ("pdf", "docx"):
            raise ValidationException(
                f"Unsupported document format '{ext}'. Only PDF (.pdf) and Word (.docx) resumes are supported.",
                code="ERR_UNSUPPORTED_DOCUMENT_TYPE",
            )

        file_bytes = await file.read()
        file_size = len(file_bytes)

        # File security checks
        validate_file_size(file_bytes, max_size_bytes=MAX_FILE_SIZE_BYTES)
        check_dangerous_executables(file_bytes[:1024])

        mime_type = "application/pdf" if ext == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        if ext == "pdf":
            validate_pdf_content(file_bytes)
        elif ext == "docx":
            validate_docx_content(file_bytes)

        # Malware scan
        scanner = get_malware_scanner()
        scan_res = await scanner.scan(file_bytes, filename=clean_filename)
        if not scan_res.is_clean:
            raise ValidationException(
                f"Document failed security scan: {scan_res.threat_name}",
                code="ERR_MALWARE_DETECTED",
            )
        malware_status = "passed" if scan_res.scanned else "passed_development_mode"

        content_sha256 = hashlib.sha256(file_bytes).hexdigest()

        # Check for existing duplicate resume uploaded by this candidate
        dup_res = await db.execute(
            select(CandidateResume).where(
                CandidateResume.user_id == user_id,
                CandidateResume.content_sha256 == content_sha256,
            )
        )
        existing = dup_res.scalar_one_or_none()
        if existing:
            raw_mime = getattr(existing, "mime_type", "application/pdf")
            resolved_mime = raw_mime if isinstance(raw_mime, str) else "application/pdf"
            raw_skills = getattr(existing, "skills_extracted", [])
            resolved_skills = raw_skills if isinstance(raw_skills, list) else []
            return ResumeUploadResponse(
                id=existing.id,
                filename=existing.filename,
                file_size_bytes=existing.file_size_bytes,
                content_sha256=existing.content_sha256,
                mime_type=resolved_mime,
                status=existing.status,
                version_number=existing.version_number,
                is_default=existing.is_default,
                is_duplicate=True,
                message="Duplicate resume detected. Using existing uploaded version.",
                skills_extracted=resolved_skills,
                ocr_applied=False,
                ocr_provider="null_ocr_unconfigured",
                malware_scan_status=malware_status,
            )

        # Determine version number
        count_res = await db.execute(
            select(func.count(CandidateResume.id)).where(CandidateResume.user_id == user_id)
        )
        existing_count = count_res.scalar() or 0
        version_number = existing_count + 1
        is_default = existing_count == 0  # First resume is automatically default

        # Generate storage key
        now = datetime.now(UTC)
        random_name = generate_secure_storage_name(ext)
        storage_key = f"candidates/{user_id}/resumes/{now.year}/{now.month:02d}/{random_name}"

        # Upload to StorageService
        self._storage.upload_document_bytes(
            file_bytes=file_bytes,
            storage_key=storage_key,
            mime_type=mime_type,
            expected_sha256=content_sha256,
        )

        # Extract text and skills synchronously
        extracted_text: str | None = None
        extracted_skills: list[str] = []
        resume_status = CandidateResumeStatus.COMPLETED.value
        error_msg: str | None = None

        if ext == "pdf":
            try:
                extraction = self._extractor.extract_from_bytes(file_bytes)
                extracted_text = extraction.raw_text
                if extracted_text and len(extracted_text.strip()) > 0:
                    parsed_data = parse_resume_text(extracted_text, self._matcher)
                    extracted_skills = parsed_data.skills
                else:
                    resume_status = CandidateResumeStatus.FAILED.value
                    error_msg = "No readable text found in PDF (scanned or image-only document; OCR is currently unconfigured)"
            except Exception as exc:
                logger.warning("Failed to extract resume text synchronously: %s", exc)
                resume_status = CandidateResumeStatus.FAILED.value
                error_msg = str(exc)
        elif ext == "docx":
            try:
                extracted_text = self._docx_extractor.extract_from_bytes(file_bytes)
                if extracted_text and len(extracted_text.strip()) > 0:
                    parsed_data = parse_resume_text(extracted_text, self._matcher)
                    extracted_skills = parsed_data.skills
                else:
                    resume_status = CandidateResumeStatus.FAILED.value
                    error_msg = "No readable text found in Word document"
            except Exception as exc:
                logger.warning("Failed to extract DOCX resume text: %s", exc)
                resume_status = CandidateResumeStatus.FAILED.value
                error_msg = str(exc)

        # Create record
        now_ts = utc_now()
        resume = CandidateResume(
            id=generate_uuid7(),
            user_id=user_id,
            storage_key=storage_key,
            filename=clean_filename,
            file_size_bytes=file_size,
            mime_type=mime_type,
            content_sha256=content_sha256,
            status=resume_status,
            version_number=version_number,
            is_default=is_default,
            extracted_text=extracted_text,
            skills_extracted=extracted_skills,
            error_message=error_msg,
            created_at=now_ts,
            updated_at=now_ts,
        )
        db.add(resume)
        await db.commit()
        await db.refresh(resume)

        return ResumeUploadResponse(
            id=resume.id,
            filename=resume.filename,
            file_size_bytes=resume.file_size_bytes,
            content_sha256=resume.content_sha256,
            mime_type=resume.mime_type,
            status=resume.status,
            version_number=resume.version_number,
            is_default=resume.is_default,
            is_duplicate=False,
            message="Resume uploaded and processed successfully",
            skills_extracted=resume.skills_extracted,
            ocr_applied=False,
            ocr_provider="null_ocr_unconfigured",
            malware_scan_status=malware_status,
        )

    async def list_resumes(self, db: AsyncSession, user_id: UUID) -> list[CandidateResumeRead]:
        """List all resumes uploaded by the candidate, annotated with active application status."""
        res = await db.execute(
            select(CandidateResume)
            .where(CandidateResume.user_id == user_id)
            .order_by(desc(CandidateResume.version_number))
        )
        resumes = res.scalars().all()
        if not resumes:
            return []

        app_res = await db.execute(
            select(JobApplication.resume_id, JobApplication.resume_snapshot_sha256).where(
                JobApplication.candidate_id == user_id
            )
        )
        raw_rows = app_res.all()
        app_rows = raw_rows if isinstance(raw_rows, list) else []
        retained_ids = {
            r[0]
            for r in app_rows
            if isinstance(r, (tuple, list)) and len(r) > 0 and r[0] is not None
        }
        retained_shas = {
            r[1]
            for r in app_rows
            if isinstance(r, (tuple, list)) and len(r) > 1 and r[1] is not None
        }

        output: list[CandidateResumeRead] = []
        for r in resumes:
            read_dto = CandidateResumeRead.model_validate(r)
            read_dto.has_active_applications = (
                r.id in retained_ids or r.content_sha256 in retained_shas
            )
            output.append(read_dto)
        return output

    async def get_resume(
        self, db: AsyncSession, user_id: UUID, resume_id: UUID
    ) -> CandidateResumeRead:
        """Retrieve resume by ID with IDOR protection."""
        res = await db.execute(
            select(CandidateResume).where(
                CandidateResume.id == resume_id,
                CandidateResume.user_id == user_id,
            )
        )
        resume = res.scalar_one_or_none()
        if not resume:
            raise EntityNotFoundException("Resume", resume_id)
        return CandidateResumeRead.model_validate(resume)

    async def get_resume_extraction(
        self, db: AsyncSession, user_id: UUID, resume_id: UUID
    ) -> ResumeExtractionResponse:
        """Retrieve extracted text and skills preview for candidate review with structured fields."""
        res = await db.execute(
            select(CandidateResume).where(
                CandidateResume.id == resume_id,
                CandidateResume.user_id == user_id,
            )
        )
        resume = res.scalar_one_or_none()
        if not resume:
            raise EntityNotFoundException("Resume", resume_id)

        raw_text = resume.extracted_text or ""
        word_count = len(raw_text.split())

        parsed_data = parse_resume_text(raw_text, self._matcher)
        if resume.skills_extracted:
            parsed_data.skills = resume.skills_extracted

        return ResumeExtractionResponse(
            resume_id=resume.id,
            status=resume.status,
            extracted_text=raw_text,
            skills_extracted=resume.skills_extracted,
            word_count=word_count,
            extracted_data=parsed_data,
            ocr_applied=False,
            ocr_provider="null_ocr_unconfigured",
            malware_scan_status="passed_development_mode",
        )

    async def update_extracted_data(
        self, db: AsyncSession, user_id: UUID, resume_id: UUID, payload: ResumeExtractedDataUpdate
    ) -> ResumeExtractionResponse:
        """Allow candidate to edit extracted skills and text snapshot, optionally syncing to profile."""
        res = await db.execute(
            select(CandidateResume).where(
                CandidateResume.id == resume_id,
                CandidateResume.user_id == user_id,
            )
        )
        resume = res.scalar_one_or_none()
        if not resume:
            raise EntityNotFoundException("Resume", resume_id)

        if payload.extracted_text is not None:
            resume.extracted_text = payload.extracted_text
        if payload.skills_extracted is not None:
            resume.skills_extracted = payload.skills_extracted

        if payload.apply_to_profile and resume.skills_extracted:
            await self.update_skills(db, user_id, resume.skills_extracted)

        await db.commit()
        await db.refresh(resume)
        word_count = len((resume.extracted_text or "").split())

        parsed_data = parse_resume_text(resume.extracted_text or "", self._matcher)
        parsed_data.skills = resume.skills_extracted

        return ResumeExtractionResponse(
            resume_id=resume.id,
            status=resume.status,
            extracted_text=resume.extracted_text,
            skills_extracted=resume.skills_extracted,
            word_count=word_count,
            extracted_data=parsed_data,
            ocr_applied=False,
            ocr_provider="null_ocr_unconfigured",
            malware_scan_status="passed_development_mode",
        )

    async def set_default_resume(
        self, db: AsyncSession, user_id: UUID, resume_id: UUID
    ) -> CandidateResumeRead:
        """Mark specific resume version as default for applications."""
        res = await db.execute(
            select(CandidateResume).where(
                CandidateResume.id == resume_id,
                CandidateResume.user_id == user_id,
            )
        )
        target = res.scalar_one_or_none()
        if not target:
            raise EntityNotFoundException("Resume", resume_id)

        # Clear is_default from all candidate's resumes
        await db.execute(
            update(CandidateResume)
            .where(CandidateResume.user_id == user_id)
            .values(is_default=False)
        )
        target.is_default = True
        await db.commit()
        await db.refresh(target)
        return CandidateResumeRead.model_validate(target)

    async def get_download_url(
        self, db: AsyncSession, user_id: UUID, resume_id: UUID
    ) -> ResumeDownloadUrlResponse:
        """Generate time-limited presigned S3 download URL."""
        res = await db.execute(
            select(CandidateResume).where(
                CandidateResume.id == resume_id,
                CandidateResume.user_id == user_id,
            )
        )
        resume = res.scalar_one_or_none()
        if not resume:
            raise EntityNotFoundException("Resume", resume_id)

        url = self._storage.generate_presigned_download_url(
            storage_key=resume.storage_key,
            expires_in_seconds=900,
        )
        return ResumeDownloadUrlResponse(
            resume_id=resume.id,
            download_url=url,
            expires_in_seconds=900,
        )

    async def delete_resume(self, db: AsyncSession, user_id: UUID, resume_id: UUID) -> None:
        """Delete resume record and remove from storage conforming to defensibility and retention rules."""
        res = await db.execute(
            select(CandidateResume).where(
                CandidateResume.id == resume_id,
                CandidateResume.user_id == user_id,
            )
        )
        resume = res.scalar_one_or_none()
        if not resume:
            raise EntityNotFoundException("Resume", resume_id)

        # Defensibility & Retention Check:
        # Check if this resume version is linked to any submitted job applications
        app_res = await db.execute(
            select(func.count(JobApplication.id)).where(
                (JobApplication.resume_id == resume.id)
                | (JobApplication.resume_snapshot_sha256 == resume.content_sha256)
            )
        )
        raw_count = app_res.scalar()
        app_count = int(raw_count) if isinstance(raw_count, (int, float)) else 0
        if app_count > 0:
            raise ValidationException(
                f"Cannot delete resume '{resume.filename}' (version {resume.version_number}): "
                f"This document is retained under compliance and audit rules because it is associated with "
                f"{app_count} submitted job application(s).",
                code="ERR_RESUME_RETAINED_FOR_APPLICATIONS",
            )

        was_default = resume.is_default

        # Delete from object storage
        self._storage.delete_document_object(resume.storage_key)

        await db.delete(resume)

        # If deleted resume was default, reassign default to the most recent remaining resume
        if was_default:
            remaining_res = await db.execute(
                select(CandidateResume)
                .where(CandidateResume.user_id == user_id)
                .order_by(desc(CandidateResume.version_number))
                .limit(1)
            )
            new_default = remaining_res.scalar_one_or_none()
            if new_default:
                new_default.is_default = True

        await db.commit()

    # -------------------------------------------------------------------------
    # Notifications Center
    # -------------------------------------------------------------------------
    async def list_notifications(
        self, db: AsyncSession, user_id: UUID
    ) -> CandidateNotificationsResponse:
        """List notifications for candidate."""
        res = await db.execute(
            select(CandidateNotification)
            .where(CandidateNotification.user_id == user_id)
            .order_by(desc(CandidateNotification.created_at))
        )
        items = res.scalars().all()
        read_items = [CandidateNotificationRead.model_validate(n) for n in items]
        unread_count = sum(1 for n in items if not n.is_read)
        return CandidateNotificationsResponse(
            notifications=read_items,
            unread_count=unread_count,
        )

    async def mark_notification_read(
        self, db: AsyncSession, user_id: UUID, notification_id: UUID
    ) -> None:
        """Mark notification as read."""
        res = await db.execute(
            select(CandidateNotification).where(
                CandidateNotification.id == notification_id,
                CandidateNotification.user_id == user_id,
            )
        )
        notif = res.scalar_one_or_none()
        if not notif:
            raise EntityNotFoundException("Notification", notification_id)

        notif.is_read = True
        await db.commit()

    async def mark_all_notifications_read(self, db: AsyncSession, user_id: UUID) -> None:
        """Mark all candidate notifications as read."""
        await db.execute(
            update(CandidateNotification)
            .where(CandidateNotification.user_id == user_id)
            .values(is_read=True)
        )
        await db.commit()

    async def create_notification(
        self,
        db: AsyncSession,
        user_id: UUID,
        title: str,
        message: str,
        category: str = "general",
        action_url: str | None = None,
    ) -> CandidateNotification:
        """Helper to create candidate notification."""
        notif = CandidateNotification(
            id=generate_uuid7(),
            user_id=user_id,
            title=title,
            message=message,
            category=category,
            is_read=False,
            action_url=action_url,
        )
        db.add(notif)
        await db.commit()
        await db.refresh(notif)
        return notif


candidate_service = CandidateService()
