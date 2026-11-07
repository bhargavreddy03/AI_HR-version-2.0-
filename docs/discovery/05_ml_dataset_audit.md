# ML Dataset Audit & Verification

This document provides verified dataset statistics, column metadata, quality metrics, and exact label-generation analysis based on direct programmatic and static code inspection of `resume_dataset_1200.csv` and `preprocessing.py`.

---

## 1. Verified Dataset Dimensions

- **Data File Path**: `resume_dataset_1200.csv`
- **Total Row Count**: Exactly **1,200** candidate rows (excluding the 1 header row).
- **Total Column Count**: Exactly **14** columns.
  *(Correction note: The initial audit draft erroneously stated 20 columns; verified inspection confirms exactly 14 columns).*
- **Exact Duplicate Records**: **0** duplicate rows across all 14 columns.

---

## 2. Comprehensive Column-by-Column Inventory

The table below outlines each of the 14 columns, their inferred data types, null/missing counts, empty/`"None"` string representations, and cardinality:

| Index | Column Name | Inferred Type | Python / Pandas Type | Empty / `"None"` Count | Missing % | Unique Count | Sample Values |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---|
| 0 | `Name` | string | `object` | 0 | 0.0% | 967 | `"Akash Pillai"`, `"Charlotte Taylor"` |
| 1 | `Age` | integer | `int64` | 0 | 0.0% | 25 | `30`, `27`, `45`, `28` (range: 21–45) |
| 2 | `Gender` | categorical string | `object` | 0 | 0.0% | 3 | `"Non-Binary"`, `"Male"`, `"Female"` |
| 3 | `Education_Level` | categorical string | `object` | 0 | 0.0% | 6 | `"Bachelor's"`, `"Master's"`, `"PhD"`, `"Diploma"`, `"Certificate"`, `"High School"` |
| 4 | `Field_of_Study` | categorical string | `object` | 0 | 0.0% | 38 | `"Computer Science"`, `"Cybersecurity"`, `"Robotics"` |
| 5 | `Degrees` | string | `object` | 0 | 0.0% | 322 | `"Master's in Cybersecurity"`, `"Bachelor's in CS"` |
| 6 | `Institute_Name` | string | `object` | 0 | 0.0% | 32 | `"University of Pennsylvania"`, `"Stanford University"` |
| 7 | `Graduation_Year` | integer | `int64` | 0 | 0.0% | 11 | `2015` to `2025` |
| 8 | `Experience_Years`| integer | `int64` | 0 | 0.0% | 11 | `0` to `10` |
| 9 | `Current_Job_Title`| string | `object` | 441 | 36.75% | 46 | `"Cybersecurity Engineer"`, `"Prompt Engineer"`, `"None"` (441 rows) |
| 10 | `Previous_Job_Titles`| string | `object` | 914 | 76.17% | 154 | `"Site Reliability Engineer"`, `"None"` (914 rows) |
| 11 | `Skills` | string (comma-separated)| `object` | 0 | 0.0% | 1200 | All 1,200 skill combinations are unique |
| 12 | `Certifications` | string (comma-separated)| `object` | 319 | 26.58% | 511 | `"Google Cloud Professional"`, `"None"` (319 rows) |
| 13 | `Target_Job_Description`| free text string | `object` | 0 | 0.0% | 333 | Candidate objective / target role descriptions |

---

## 3. Synthetic Target Variable & Exact Label Generation Methodology

The dataset file `resume_dataset_1200.csv` **does not contain a native ground-truth target column**.
The binary target variable `y` (`0 = Not Suitable`, `1 = Suitable`) is **programmatically and synthetically constructed** at runtime within `preprocessing.py` via `_compute_hr_score(row)` and `build_target(df, cfg)`:

### A. Continuous Score Formulation (`_compute_hr_score`)
Located at `preprocessing.py:197-240`, a continuous suitability score (approximate range $[1.0, 10.0]$) is computed by evaluating a weighted linear combination with interactions and non-linear penalties:

$$\begin{aligned}
\text{hr\_score} = &\; 2.60 \cdot \text{exp\_norm} + 2.10 \cdot \text{edu\_norm} + 1.60 \cdot \text{skill\_norm} + 1.10 \cdot \text{has\_cert} \\
&+ 0.90 \cdot \text{f\_sc} + 0.80 \cdot \text{t\_sc} + 0.70 \cdot \text{best\_cl} \\
&+ 0.50 \cdot (\text{exp\_norm} \times \text{edu\_norm}) + 0.40 \cdot (\text{skill\_norm} \times \text{has\_cert}) \\
&+ 0.30 \cdot (\text{f\_sc} \times \text{edu\_norm}) - 0.25 \cdot \max\left(0, \frac{\text{Age} - 45}{5.0}\right)
\end{aligned}$$

Where:
- $\text{exp\_norm} = \ln(1 + \text{exp}) / \ln(1 + 12)$ (logarithmic scale, plateauing at 12 years).
- $\text{edu\_norm} = (\text{edu\_level} - 1) / 5.0$ mapping `High School (1)` to `PhD (6)`.
- $\text{skill\_norm} = \min(\text{len}(\text{skills}) / 10.0, 1.0)$.
- $\text{has\_cert} = 1$ if `Certifications` not in `("None", "nan", "")`, else $0$.
- $\text{f\_sc} \in [0.25, 1.0]$ based on `FIELD_SCORE_MAP`.
- $\text{t\_sc} \in [0.50, 1.0]$ based on `TITLE_SCORE_MAP`.
- $\text{best\_cl} \in [0.0, 1.0]$ coverage of the candidate's highest covered domain stack (ML, Cloud, Data, DevOps, Web, Security).
- **Age Penalty Term Analysis**:
  - The formula specifies: $- 0.25 \times \max\left(0, \frac{\text{Age} - 45}{5.0}\right)$.
  - **Critical Dataset Reality**: In `resume_dataset_1200.csv`, candidate ages range strictly between **21 and 45** inclusive (maximum age observed is exactly 45).
  - Consequently, for every record in the current dataset, $\max(0, (\text{Age} - 45)/5.0) = 0$.
  - **Impact**: This penalty term evaluates to **exactly 0.0 across all 1,200 records in the dataset**. It has **not altered the target labels of any existing records**. However, its architectural presence in the codebase represents an intentional age-penalty logic that must be completely removed before deploying to production to ensure strict regulatory compliance (e.g. EEOC / ADEA).

### B. Raw Deterministic Labels vs. Calibrated Noise (`build_target`)
Located at `preprocessing.py:243-270`:
1. **Deterministic Cutoff**: Candidates with $\text{hr\_score} \ge 5.0$ are initially assigned `1` (Suitable), else `0` (Not Suitable).
   - **Raw Deterministic Distribution**:
     - `Suitable (1)`: **835** candidates (69.58%)
     - `Not Suitable (0)`: **365** candidates (30.42%)
2. **Why Calibrated Label Noise is Injected**:
   - Because the labels are derived from a mathematical formula of input features, a decision tree would trivially achieve near 100% accuracy without learning real-world recruitment ambiguity.
   - To simulate human recruiter disagreement and borderline review variance, stochastic label flipping is introduced using `numpy.random.default_rng(cfg.random_state=42)`:
     - Base flip rate: $\text{flip\_rate\_base} = 0.06$ (6%).
     - Borderline flip rate: For candidates whose $|\text{hr\_score} - 5.0| < 0.8$, the flip probability increases to $0.06 + 0.15 = 0.21$ (21%).
3. **Resulting Target Distribution**:
   - Injected flips: Approximately **120–140** candidate labels are inverted.
   - Final Target Split: ~**65.0% Suitable (1)** and **35.0% Not Suitable (0)**.
   - Stratification: Maintained in train/test splits (`stratify=y`).

---

## 4. Assessment for Enterprise SaaS

1. **Synthetic Nature**: Both feature inputs (templated CSV) and target labels are artificially constructed. The models are learning to approximate the noisy synthetic formula in `preprocessing.py`, rather than empirical human hiring outcomes.
2. **Regulatory Risk**: Although the age penalty contributes 0 to the current dataset scores due to the observed age ceiling ($\le 45$), the logic exists in the code and must be eliminated in any production scoring service.
3. **Enterprise Path**: In the target Modular Monolith, candidate suitability scoring will rely on transparent, explainable skill-matching rubrics and vector similarity (`pgvector`) against job descriptions, combined with structured human-in-the-loop recruiter reviews.
