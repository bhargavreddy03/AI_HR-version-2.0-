# Functionality Inventory & Source Reconciliation

This document provides a verified, code-level reconciliation of every feature present in the AI HR application (`app.py`, `hr_agent.py`, `skill_extractor.py`, `question_generator.py`, `preprocessing.py`, `utils.py`).

Every feature is classified strictly according to verified implementation reality:
- **Implemented**: Fully coded and operational with local logic.
- **Partially Implemented**: Working, but contains limitations, manual steps, or incomplete domain rules.
- **Prototype**: Placeholder logic, in-memory simulations, or stubs requiring external infrastructure/APIs.
- **Unverified / Absent**: Claimed in high-level discussions or missing entirely.

---

## 1. Feature-by-Feature Reconciliation Matrix

| Feature Domain | Feature Name | Implementation Status | Source Reference | Exact Implementation Details & Limitations |
|:---|:---|:---:|:---|:---|
| **Navigation & UI** | Sidebar Navigation | **Implemented** | `app.py:265-300` | Streamlit `st.radio` rendering 8 views: `🏠 Overview`, `🧠 Train ML Models`, `📊 Analytics Dashboard`, `📄 Resume Screening`, `🗓 Interview Scheduling`, `❓ Question Generator`, `🔄 Pipeline Manager`, `📤 Export Results`. |
| **Ingestion** | Resume File Types | **Implemented (PDF Only)** | `app.py:677-682` | Only `.pdf` is accepted by `st.file_uploader(type=["pdf"])`. DOCX/TXT uploads are **not implemented** in the UI. |
| **Ingestion** | Text Extraction | **Implemented** | `app.py:33-49` | `extract_text_from_pdf()` tries `pdfplumber`, falls back to `PyPDF2`, then raw UTF-8 byte decode. No OCR support for scanned/image PDFs. |
| **Information Extraction** | Name & Experience Extraction | **Partially Implemented** | `app.py:51-73` | Regex heuristic rules: `guess_name_from_text()` looks for uppercase Title Case lines; `guess_experience_from_text()` searches for `\d+(\.\d+)? years of experience`. Fragile on complex resume layouts. |
| **Information Extraction** | Skill Extraction | **Implemented** | `skill_extractor.py:1-647` | Multi-tiered `SkillExtractor` utilizing taxonomy lookup (`SkillRegistry`), regex normalization, and exact word boundary token matching across 250+ canonical skills. |
| **Recruitment Logic** | Candidate Ranking | **Implemented (Deterministic)** | `hr_agent.py:122-156` | `ResumeRanker.rank_candidates()` computes: $0.55 \times \text{coverage} + 0.10 \times \text{kw\_sim} + 0.10 \times \text{breadth} + 0.25 \times \text{exp\_sc}$. Note: Does **not** use the trained ML models from `train_models.py` for ranking! |
| **Recruitment Logic** | ML Candidate Scoring | **Implemented (Isolated)** | `app.py:465-490`, `train_models.py:727-740` | ML inference exists on the `Train ML Models` / `Analytics Dashboard` pages to show model comparison charts and confusion matrices, but candidate ranking on the screening page is powered entirely by the deterministic heuristic formula. |
| **Interview Management** | Interview Scheduling | **Prototype** | `hr_agent.py:162-190`, `app.py:850-980` | Generates a static in-memory list of dates for the next 7 days (`_generate_available_slots()`). Assigns slots by `.pop(0)`. No Google Calendar, Outlook, or external calendar sync. |
| **Assessment** | Question Generation (Rule-based) | **Implemented** | `question_generator.py:1-450`, `hr_agent.py:288-312` | Heuristic template generator: routes by skill and candidate seniority (Junior, Mid, Senior, Lead). Selects conceptual, scenario, coding, and behavioral questions from a hardcoded question bank. |
| **Assessment** | Question Generation (LLM) | **Prototype** | `question_generator.py:700-800` | `LLMQuestionGenerator` calls external provider (OpenAI/Anthropic compatible stub). Returns mock questions if API key is unset. |
| **Pipeline Tracking** | Hiring Stage Pipeline Manager | **Implemented (In-Memory)** | `hr_agent.py:196-244`, `app.py:1180-1370` | Finite State Machine with transitions: `applied` $\rightarrow$ `shortlisted` $\rightarrow$ `interview_scheduled` $\rightarrow$ `interviewed` $\rightarrow$ `selected` / `rejected`. Enforces `VALID_TRANSITIONS`. |
| **Reporting & Export** | Excel Pipeline Export | **Implemented** | `app.py:1451-1493` | Generates `.xlsx` via `openpyxl` buffer containing up to 4 sheets (`Candidate Pipeline`, `Scheduled Interviews`, `ML Model Results`, `Interview Questions`). Downloadable via `st.download_button`. |
| **Persistence** | Data Persistence | **Prototype / In-Memory Only** | `app.py:235-251` | All state resides in `st.session_state`. Reset on browser reload or app reboot. |
| **Security & Auth** | User Authentication | **Absent / Not Implemented** | N/A | No login, session tokens, or RBAC. The app runs fully open. |
| **Multi-Tenancy** | Tenant Isolation | **Absent / Not Implemented** | N/A | Single global in-memory workspace. |

---

## 2. Key Reconciliation Corrections

1. **ML Model vs. Heuristic Ranking Disconnection**:
   - In previous summaries, it was assumed that `HRAgent` scores uploaded resumes using the serialized `.pkl` models (`best_model_name.pkl`).
   - Code inspection reveals that `ResumeRanker.rank_candidates()` (`hr_agent.py:122-156`) calculates ranking scores via deterministic Jaccard and coverage overlap formulas against JD skills. The ML models are trained and showcased on their own dashboard tabs, but are **not** invoked in the primary candidate ranking loop.
2. **File Support**:
   - Streamlit accepts `.pdf` only (`app.py:679`). Earlier mentions of DOCX/TXT uploads are invalid for the current code.
3. **Export Functionality**:
   - The initial draft stated export functionality could not be found. Verified inspection shows `app.py:1374-1493` provides a complete multi-sheet Excel export via `openpyxl`.
