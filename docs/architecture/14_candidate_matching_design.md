# Candidate-Job Matching Architecture & Scoring Design

This document details the explainable candidate-job matching engine, component weighting formula, vector semantic similarity calculation, and transparent reporting models.

---

## 1. Explainable Matching Formulation

Candidate matching evaluates candidate qualifications against a job requisition through an explainable, multi-factor weighted equation:

$$\text{Overall Match Score} = \sum_{i=1}^{5} \left( w_i \times S_i \right)$$

### Default Illustrative Component Weights ($w_i$):
1. **$S_{\text{req}}$: Required Skills Match ($w_1 = 0.40$)**
   - Evaluates the proportion of mandatory job skills present in the candidate profile:
   $$S_{\text{req}} = \frac{|\text{Candidate Skills} \cap \text{Required Job Skills}|}{|\text{Required Job Skills}|}$$
   - *Hard Gate Constraint*: If any mandatory skill is absent, $S_{\text{req}}$ decreases proportionally, and the missing skill is highlighted in red on recruiter dashboards.

2. **$S_{\text{exp}}$: Relevant Experience Match ($w_2 = 0.25$)**
   - Compares candidate verified years of experience ($E_{\text{cand}}$) against the job's minimum experience threshold ($E_{\text{req}}$):
   $$S_{\text{exp}} = \begin{cases} 
   1.0 & \text{if } E_{\text{cand}} \ge E_{\text{req}} \\
   \frac{E_{\text{cand}}}{E_{\text{req}}} & \text{if } E_{\text{cand}} < E_{\text{req}}
   \end{cases}$$

3. **$S_{\text{qual}}$: Qualifications & Education Match ($w_3 = 0.15$)**
   - Evaluates education tier alignment (Degree, Field of Study) and required professional certifications (e.g. AWS Solutions Architect, PMP).

4. **$S_{\text{pref}}$: Preferred Skills Match ($w_4 = 0.10$)**
   - Measures candidate overlap with optional / "nice-to-have" job skills.

5. **$S_{\text{align}}$: Semantic & Role Alignment ($w_5 = 0.10$)**
   - Computed via cosine similarity between the candidate resume embedding $\vec{v}_{\text{resume}}$ and job description embedding $\vec{v}_{\text{job}}$:
   $$S_{\text{align}} = \frac{\vec{v}_{\text{resume}} \cdot \vec{v}_{\text{job}}}{\|\vec{v}_{\text{resume}}\| \|\vec{v}_{\text{job}}\|}$$

*Note: Component weights are fully configurable per job requisition in `jobs.weights_config`.*

---

## 2. Transparent Screening Report Structure

Each screening execution produces an auditable record in `screening_results`:

```json
{
  "application_id": "app-0001-1111-2222-3333-444455556666",
  "candidate_name": "Jordan Lee",
  "overall_match_score": 0.8650,
  "component_breakdown": {
    "required_skills": { "score": 1.00, "weight": 0.40, "weighted": 0.400 },
    "experience":        { "score": 0.80, "weight": 0.25, "weighted": 0.200 },
    "qualifications":    { "score": 1.00, "weight": 0.15, "weighted": 0.150 },
    "preferred_skills":  { "score": 0.50, "weight": 0.10, "weighted": 0.050 },
    "role_alignment":    { "score": 0.65, "weight": 0.10, "weighted": 0.065 }
  },
  "skills_analysis": {
    "matched_required": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "missing_required": [],
    "matched_preferred": ["Redis"],
    "missing_preferred": ["Celery", "pgvector"]
  },
  "verifiable_evidence": [
    {
      "skill": "FastAPI",
      "resume_context": "Architected high-throughput asynchronous REST APIs using FastAPI and SQLAlchemy."
    }
  ],
  "compliance_statement": "This assessment is grounded strictly in job description criteria and verified resume evidence. Sensitive demographic characteristics were not utilized in this evaluation."
}
```
