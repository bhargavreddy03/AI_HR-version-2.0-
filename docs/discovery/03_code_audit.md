# Code Audit

This document provides a per-module static code audit of the AI HR application, detailing exact responsibilities, implementation status, and source references.

---

## 1. Module-by-Module Audit

### A. `app.py`
- **Purpose**: Main Streamlit user interface, routing controller, and dashboard view renderer.
- **Key Sections**:
  - `app.py:33-49`: `extract_text_from_pdf()` provides PDF text extraction using `pdfplumber` with fallback to `PyPDF2`.
  - `app.py:51-73`: `guess_name_from_text()` and `guess_experience_from_text()` extract candidate metadata via regex patterns.
  - `app.py:79-84`: Page configuration (`st.set_page_config`) setting title, icon, and wide layout.
  - `app.py:235-251`: Initializes default in-memory keys in `st.session_state`.
  - `app.py:288-300`: Sidebar navigation rendering 8 view radios: `🏠 Overview`, `🧠 Train ML Models`, `📊 Analytics Dashboard`, `📄 Resume Screening`, `🗓 Interview Scheduling`, `❓ Question Generator`, `🔄 Pipeline Manager`, `📤 Export Results`.
  - `app.py:674-750`: PDF resume upload tab (`type=["pdf"]`).
  - `app.py:1451-1493`: Multi-sheet Excel export via `openpyxl` buffer.
- **Implementation Reality**:
  - File format: Accepts **PDF only**; claims of DOCX/TXT upload are not supported in code.
  - State: Strictly transient; reset upon browser reload.
  - Model usage: ML models are displayed on training and analytics tabs, not executed in the resume screening flow.
- **Source Reference**: `app.py:1-1493`

---

### B. `hr_agent.py`
- **Purpose**: Business logic layer defining recruitment ranking, candidate pipeline tracking, interview scheduling, and question routing.
- **Core Classes**:
  - `ResumeRanker` (`hr_agent.py:69-156`): Extracts skills via `SkillExtractor` and computes candidate match scores using a deterministic weighted combination of JD skill coverage (0.55), keyword similarity (0.10), skill breadth bonus (0.10), and experience match (0.25).
  - `PipelineManager` (`hr_agent.py:196-244`): Implements an in-memory finite state machine enforcing transitions across `applied`, `shortlisted`, `interview_scheduled`, `interviewed`, `selected`, and `rejected`.
  - `InterviewScheduler` (`hr_agent.py:162-190`): Generates a list of slots for the next 7 days (`_generate_available_slots`) and assigns them sequentially.
  - `HRAgent` (`hr_agent.py:250-377`): Master coordinator tying ranker, pipeline manager, scheduler, and question generator together.
- **Implementation Reality**:
  - Ranking is **deterministic and heuristic**; no machine learning model is invoked for candidate ranking.
  - Interview scheduling is an in-memory prototype without real calendar integration.
- **Source Reference**: `hr_agent.py:1-401`

---

### C. `skill_extractor.py`
- **Purpose**: Normalizes text and extracts technical skills based on a predefined dictionary.
- **Key Classes**:
  - `SkillRegistry` (`skill_extractor.py:25-90`): Loads taxonomy JSON and resolves aliases (e.g. `"reactjs"` $\rightarrow$ `"React"`, `"k8s"` $\rightarrow$ `"Kubernetes"`).
  - `ExactMatcher` (`skill_extractor.py:95-150`): Word-boundary regex matching against 250+ canonical skills.
  - `SemanticMatcher` (`skill_extractor.py:160-220`): Optional `sentence-transformers` similarity matcher, guarded by configuration.
  - `SkillExtractor` (`skill_extractor.py:230-647`): Coordinates exact and optional semantic matching to return canonical skill lists.
- **Implementation Reality**: Fully implemented and standalone; 100% reusable outside Streamlit.
- **Source Reference**: `skill_extractor.py:1-647`

---

### D. `question_generator.py`
- **Purpose**: Generates interview questions tailored to candidate skills and experience levels.
- **Key Classes**:
  - `QuestionGenerator` / `QuestionEngine` (`question_generator.py:1-450`): Selects questions from an internal categorized question bank across Conceptual, Coding, Scenario, System Design, and Behavioral types. Adjusts questions based on seniority tiers (Junior, Mid, Senior, Lead).
  - `LLMQuestionGenerator` (`question_generator.py:700-800`): Stubbed integration for calling an external LLM API. Falls back to static question templates when an API key is absent.
- **Implementation Reality**: Rule-based template generator is fully implemented; LLM integration is a prototype stub.
- **Source Reference**: `question_generator.py:1-800`

---

### E. `preprocessing.py`
- **Purpose**: Feature extraction, dataset cleaning, target label construction, scaling, and feature selection.
- **Key Components**:
  - `_compute_hr_score()` & `build_target()` (`preprocessing.py:197-270`): Synthetically creates the binary target variable from a continuous weighted formula with distance-calibrated noise flips.
  - `build_features()` (`preprocessing.py:275-362`): Constructs 79 raw features covering numeric metadata, polynomial interaction terms, skill cluster coverage, and one-hot skill flags.
  - `ResumePreprocessor` (`preprocessing.py:366-493`): Fits `SimpleImputer`, `PowerTransformer`, `RobustScaler`, and `VarianceThreshold` (79 raw $\rightarrow$ 37 features).
  - `apply_smote()` (`preprocessing.py:497-513`): Over-samples the training set using SMOTE.
- **Implementation Reality**: Code executes as designed, but suffers from severe pre-split data leakage as all transformers are fitted globally before the train/test split.
- **Source Reference**: `preprocessing.py:1-564`

---

### F. `train_models.py`
- **Purpose**: End-to-end model training, cross-validation, evaluation metric generation, and model artifact serialization.
- **Key Components**:
  - `get_models()` (`train_models.py:77-115`): Instantiates `RandomForest`, `LogisticRegression`, `LinearSVC`, `KNN`, `GradientBoosting`, `MLP`, and optional `XGBoost`.
  - `ModelTrainer` (`train_models.py:145-346`): Fits models, computes classification reports, calculates 5-fold CV, and selects the best model based on `test_accuracy`.
  - Dark-theme graph generators (`train_models.py:348-722`): Saves 16 PNG visualization charts to `static/graphs/`.
- **Implementation Reality**: Training pipeline runs completely, but the evaluation methodology is compromised by pre-split leakage and model selection on the holdout test set.
- **Source Reference**: `train_models.py:1-760`

---

### G. `utils.py`
- **Purpose**: Shared utilities for data loading, JSON serialization, status badges, and graph paths.
- **Key Functions**:
  - `load_csv_candidates()` (`utils.py:43-88`): Samples rows with a fixed `random_state=42` and builds structured candidate dictionaries.
  - `summarise_results()` (`utils.py:184-205`): Tabulates training metric dictionaries into a sorted DataFrame.
  - `get_graph_path()` / `graphs_exist()` (`utils.py:157-170`): Manages graph file paths in `static/graphs/`.
- **Source Reference**: `utils.py:1-205`
