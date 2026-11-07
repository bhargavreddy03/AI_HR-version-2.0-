# Verified Reusable Components Inventory

This document details all verified classes, functions, and modules across the codebase that can be extracted and reused in the target Modular Monolith backend.

Every component below has been statically verified against source code definitions for exact method signatures, argument types, return types, dependencies, side effects, and reusability outside Streamlit.

---

## 1. Component Verification Matrix

### A. `SkillRegistry` & `SkillExtractor`
- **Location**: `skill_extractor.py:25-647`
- **Genuine Reusability**: **High (100% reusable outside Streamlit)**. Clean pure-Python logic with standard libraries and regex.

#### Exact Signatures:
1. `SkillRegistry.get_canonical(alias: str) -> Optional[str]`
   - **Inputs**: Raw skill string or alias (e.g. `"reactjs"`, `"k8s"`).
   - **Returns**: Canonicalized string name (`"React"`, `"Kubernetes"`), or `None`.
   - **Dependencies**: Internal taxonomy dict.
   - **Side Effects**: None.
2. `SkillExtractor.extract(text: str) -> List[str]`
   - **Inputs**: Arbitrary string (resume text, job description text).
   - **Returns**: List of sorted unique canonical skill names detected in text.
   - **Dependencies**: `SkillRegistry`, `re`.
   - **Side Effects**: None (pure transformation function).
3. `SkillExtractor.extract_with_categories(text: str) -> Dict[str, List[str]]`
   - **Inputs**: String resume text.
   - **Returns**: Dictionary grouping detected skills by category (`"Frontend"`, `"Cloud"`, etc.).
   - **Dependencies**: Category mappings.
   - **Side Effects**: None.

---

### B. `ResumeRanker`
- **Location**: `hr_agent.py:69-156`
- **Genuine Reusability**: **High (Reusable in backend service layer)**.

#### Exact Signatures:
1. `ResumeRanker.compute_jd_coverage(resume_skills: List[str], jd_skills: List[str]) -> float`
   - **Inputs**: Lists of extracted skill strings.
   - **Returns**: Float ratio in $[0.0, 1.0]$.
   - **Side Effects**: None.
2. `ResumeRanker.compute_keyword_similarity(resume_skills: List[str], jd_skills: List[str]) -> float`
   - **Inputs**: Lists of extracted skill strings.
   - **Returns**: Jaccard similarity float in $[0.0, 1.0]$.
   - **Side Effects**: None.
3. `ResumeRanker.compute_experience_score(exp_years: float, jd_text: str) -> float`
   - **Inputs**: Float candidate years of experience, string JD text.
   - **Returns**: Experience match score float in $[0.0, 1.0]$.
   - **Side Effects**: None.
4. `ResumeRanker.rank_candidates(candidates: List[Dict], jd_text: str) -> List[Dict]`
   - **Inputs**: 
     - `candidates`: List of dicts containing `{"id": Any, "resume_text": str, "experience_years": float}`.
     - `jd_text`: String job description text.
   - **Returns**: List of candidate dicts enriched with `"skills"`, `"match_score"`, and `"rank"`, sorted descending by match score.
   - **Dependencies**: `SkillExtractor`.
   - **Side Effects**: None.

---

### C. `PipelineManager`
- **Location**: `hr_agent.py:196-244`
- **Genuine Reusability**: **Moderate (Encapsulates valid domain state transitions; needs DB persistence in SaaS)**.

#### Exact Signatures:
1. `PipelineManager.add_candidate(candidate_id: str) -> Dict[str, Any]`
   - **Returns**: `{"candidate_id": str, "state": "applied", "success": True}`.
2. `PipelineManager.transition(candidate_id: str, new_state: str) -> Dict[str, Any]`
   - **Inputs**: `candidate_id: str`, `new_state: str`.
   - **Returns**: Status dict indicating success or error if transition violates `VALID_TRANSITIONS`.
   - **Dependencies**: `VALID_TRANSITIONS` state table.
   - **Side Effects**: Modifies in-memory `self.pipeline` dict. Must be backed by PostgreSQL transaction in target architecture.

---

### D. `QuestionGenerator`
- **Location**: `question_generator.py:1-800`
- **Genuine Reusability**: **High (Reusable inside assessment service)**.

#### Exact Signatures:
1. `QuestionGenerator.generate(skills: List[str], n_per_skill: int = 3, experience_years: float = 0.0, jd_text: str = "", name: str = "Candidate") -> List[Dict]`
   - **Inputs**: List of skill strings, question count per skill, candidate experience float, JD text string, candidate name string.
   - **Returns**: List of question dicts with keys `{"id", "skill", "type", "question", "difficulty", "seniority_tier", "expected_answer_points"}`.
   - **Dependencies**: Internal taxonomy question bank.
   - **Side Effects**: None.

---

### E. Text Extraction Helpers
- **Location**: `app.py:33-74`
- **Genuine Reusability**: **Moderate (Refactor into dedicated document parsing utility)**.

#### Exact Signatures:
1. `extract_text_from_pdf(pdf_bytes: bytes) -> str`
   - **Inputs**: Raw byte stream of PDF document.
   - **Returns**: Plain text string extracted via `pdfplumber` or `PyPDF2`.
   - **Dependencies**: `pdfplumber`, `PyPDF2`, `io`.
   - **Side Effects**: None.
2. `guess_name_from_text(text: str) -> str`
   - **Inputs**: Plain text string.
   - **Returns**: Detected candidate name string or `"Unknown Candidate"`.
3. `guess_experience_from_text(text: str) -> float`
   - **Inputs**: Plain text string.
   - **Returns**: Extracted experience years as float, or `0.0`.

---

### F. Dataset & CSV Utility Helpers
- **Location**: `utils.py:43-88, 184-205`
- **Genuine Reusability**: **Moderate (Test data loading & benchmarking)**.

#### Exact Signatures:
1. `load_csv_candidates(csv_path: str, max_rows: int = 50) -> List[Dict]`
   - **Inputs**: String path to CSV, integer max rows.
   - **Returns**: Formatted list of candidate dictionaries with keys `id`, `name`, `resume_text`, `experience_years`, `raw_skills`, `education`, `current_job`, `certifications`.
   - **Dependencies**: `pandas`.
   - **Side Effects**: File I/O.
2. `summarise_results(results: Dict) -> pd.DataFrame`
   - **Inputs**: Dictionary of training metrics across models.
   - **Returns**: Sorted `pd.DataFrame` ranking models by test accuracy.

---

## 2. Refactoring Summary for Target Backend

All above classes operate on primitive Python types (`str`, `float`, `list`, `dict`), with no hard dependency on Streamlit UI elements (`st.sidebar`, `st.button`, etc.). They can be ported directly into the domain modules of the FastAPI backend (`app/modules/screening/`, `app/modules/interviews/`, `app/modules/candidates/`).
