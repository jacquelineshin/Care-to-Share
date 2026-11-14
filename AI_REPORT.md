# Care to Share — AI Integration & Evaluation Report

Parts 3 (AI Integration) and 4 (Evaluation, Testing, and Improvement).

All numbers in this report come from the evaluation harness in the repo and can be reproduced with:

```bash
python manage.py seed_resources --embed
python manage.py evaluate_recommender --strategy baseline
python manage.py evaluate_recommender --strategy hybrid
python manage.py evaluate_recommender --strategy hybrid --cases ai_services/data/eval_cases_holdout.json
```

Raw per-case results are saved in `ai_services/data/eval_results_*.json`.

---

# Part 3 — AI Integration

## 3.1 The AI feature

**Personalized educational-resource recommendations with red-flag safety screening.**

Patients record health concerns before a visit: a symptom, a free-text description, frequency, duration, triggers, relieving factors, and a question for the doctor. Patients write these in everyday words ("room spinning", "burning when I pee", "no energy even after sleeping 9 hours"). The app matches each concern to a curated library of trustworthy educational articles (30 MedlinePlus topics). This helps the patient understand their symptom and prepare questions before the visit.

The feature has three AI/decision components that work together:

| Component | Technique | Where it shows up |
|---|---|---|
| Semantic retrieval | Sentence-embedding model (`all-MiniLM-L6-v2`) + cosine similarity over resource embeddings stored in the database | "Find Educational Resources" page for each concern |
| Confidence-aware ranking & explanation | Tiered thresholds (strong / possible / distinctive top match) + matched-term explanation ("Why this was suggested") | Badges and explanation on each recommended resource |
| Red-flag safety screen | Deterministic rule-based classifier (regex) for emergency and self-harm language | Urgent-care / 988 banner on the concern card, the resources page, and a flag on the printable pre-visit summary |

If the embedding model fails, a **keyword-overlap fallback ranker** takes over automatically (see 3.5).

## 3.2 Model selection

**Model: `sentence-transformers/all-MiniLM-L6-v2`, run locally on CPU.**

| Consideration | Why this model fits |
|---|---|
| Capability | Trained for semantic similarity on short texts, which matches 1–3 sentence symptom descriptions. It handles lay language and misspellings that keyword search misses ("Migrane" → Migraine, "room spinning" → Dizziness). |
| Compute | 22M parameters, ~90 MB, 384-dim vectors. Runs on any laptop CPU, no GPU needed. |
| Latency | ~9 ms per query when warm (p50 = 9.0 ms, p95 = 10.6 ms over 31 cases). |
| Cost | Free. No per-request API fees. |
| Privacy | **Health data never leaves the server.** No patient text is sent to a third-party API, and logs record only concern IDs, status, and latency, never symptom text. This matters a lot for health data. |
| Accuracy | Top-1 accuracy was already 100% *when it returned a result*. The weaknesses were threshold and query construction, which we fixed (Part 4). |
| Scalability | Resource embeddings are computed once and cached in `EducationalResource.embedding` (JSONField). Each request embeds only the query. A linear scan is fine up to ~10k articles. Beyond that, the vectors would move to pgvector or FAISS. |

**Why not other options?**
- **Hosted embedding API (e.g., OpenAI):** similar quality, but it sends protected health information to a third party, adds network latency and cost, and adds an outage dependency.
- **Generative LLM (chatbot answers):** risks hallucinated medical advice. We deliberately *retrieve vetted content* instead of *generating* medical text.
- **Larger embedder (`all-mpnet-base-v2`):** slightly more accurate but ~5× slower with a 768-dim index. Not needed at our library size.
- **Keyword search only (BM25):** cannot connect "can't fall asleep" to *Insomnia* or "flashing lights before it starts" to *Migraine*. We keep it only as the failure fallback.
- **ML model for safety screening:** rules were chosen on purpose. Safety must work even when the model is down, behave predictably, and be auditable line by line.

## 3.3 AI workflow

```
Patient fills HealthConcern form ─► Django form validation (symptom ≥ 3 chars, severity 1–10)
        │                                  │
        ▼                                  ▼
   saved to DB                    appointment_detail / pre_visit_summary views
        │                                  └─► safety.screen_concern()  ─► urgent banner / summary flag
        ▼
"Find Educational Resources" ─► views.recommended_resources (login + ownership check)
        │
        ▼
ai_services.resource_recommender.get_recommendations(concern)
   1. Validate input        (None / no letters → "insufficient_input")
   2. Safety screen         (regex rules → SafetyAlert: emergency 911 | crisis 988)
   3. Preprocess            build_query_text(): only filled-in fields, human labels,
                            whitespace-normalized, ≤ 3000 chars
   4. Embed query           MiniLM → 384-d L2-normalized vector, validated (dim, finite)
   5. Load resource vectors from DB; missing/corrupt ones re-embedded in one batch + bulk_update
   6. Score                 cosine similarity (dot product of normalized vectors)
   7. Postprocess           hybrid_rank(): strong ≥ 0.45 | possible ≥ 0.40 |
                            lone top ≥ 0.30 that beats runner-up by ≥ 0.10 | else nothing
                            + matched_terms() explanation
   8. Return RecommendationResult(recommendations, status, message, safety_alert, latency_ms)
        │
        ▼
Template: safety banner → status notice (fallback / error) → resource cards with
confidence badge, "why suggested", topic, source, relevance, link → disclaimer
```

**What enters the AI system?** The patient's own concern fields (symptom, description, frequency, duration, triggers, relieving factors, question). Severity is used by the UI but left out of the embedding text, because a number has no topical meaning. On the other side are the title, description, topic, and content of each library article.

**How is it prepared?** Empty fields are dropped, the frequency code becomes its human label ("several_weekly" → "Several times per week"), whitespace is collapsed, and length is capped. Resource text is concatenated and embedded once, then cached.

**Which model processes it?** `all-MiniLM-L6-v2` for retrieval, and the rule set in `ai_services/safety.py` for red flags.

**How are results generated?** Cosine similarity ranks all articles. A confidence-tiered threshold decides what to show and how to label it.

**How are results validated?**
- Every vector is checked for length 384 and finite values. Invalid output raises `EmbeddingError`, which triggers the fallback.
- Stored embeddings with the wrong shape are recomputed automatically.
- The thresholds were calibrated against a labelled evaluation set and then checked on a separate held-out set (Part 4).
- Only vetted articles from the database can be shown, so the model cannot invent content or URLs.

**How does the user receive the output?** As resource cards with a "Strong / Possible / Keyword match" badge and a "Why this was suggested" line. An honest "no close match" message appears when nothing qualifies. A red urgent-care banner (911) or purple crisis banner (988) appears above everything when a red flag is detected. The pre-visit summary the patient brings to the doctor also flags those concerns.

## 3.4 Integration depth

This is not a chatbot or an API pass-through:
- **Reads application data:** it works on `HealthConcern` records the user created, scoped to the logged-in user (another user's concern returns 404).
- **Writes application data:** article embeddings are generated and persisted to `EducationalResource.embedding`. Editing an article's text invalidates its embedding automatically (`EducationalResource.save`).
- **Retrieves from our own database** (RAG-style retrieval over a curated library) instead of generating free text.
- **Changes the workflow on three pages:** the appointment detail page (safety banner per concern), the recommendations page, and the printable pre-visit summary (flagged concerns).
- **Operational tooling:** `seed_resources` (library + embeddings), `evaluate_recommender` (offline evaluation), `seed_demo` (demo account).

## 3.5 Reliability

| Situation | Handling | Test |
|---|---|---|
| Invalid input (`"??"`, empty, `None`) | `insufficient_input` status, friendly prompt to add detail | `test_insufficient_input`, `test_none_concern` |
| Form-level invalid data | Django form validation (symptom length, severity 1–10) | existing forms |
| Missing data (empty optional fields) | Omitted from the query instead of injecting "Triggers: ." filler | `test_empty_fields_are_not_included` |
| Missing / corrupted stored embedding | Re-embedded in one batch and saved | `test_corrupted_stored_embedding_is_recomputed` |
| Model can't load (not installed, download fails, offline) | Automatic **keyword fallback** with a "Keyword match" badge and a notice to the user | `test_model_unavailable_falls_back_to_keywords` |
| Unexpected model output (NaN, wrong dimension) | `EmbeddingError` → fallback | `test_invalid_model_output_falls_back` |
| Any other runtime error (DB, bug) | Caught. `error` status with a friendly message. Page still renders. Stack trace logged without patient text | `test_unexpected_error_is_reported_not_raised`, `test_page_renders_when_model_fails` |
| Nothing relevant | `no_match` status: "We don't have a resource that closely matches…" instead of showing weak matches | `test_no_match_status_when_nothing_relevant` |
| Safety | Red-flag screen runs **before** and **independently of** the model, so it still works during model failure | `test_safety_alert_survives_model_failure` |
| Privacy | Local model. No third-party calls. Logs contain no symptom text. Per-user access control | `test_other_users_concern_is_not_accessible` |
| Medical-advice risk | Only vetted MedlinePlus articles are shown. Disclaimer states the AI matching is educational, not diagnostic | template |

Run all tests with `python manage.py test` (29 tests, all passing).

---

# Part 4 — Evaluation, Testing, and Improvement

## 4.1 Evaluation criteria

The recommender serves patients describing symptoms in their own words, and a wrong output can be unhelpful or unsafe. So we measure:

| Metric | Why it matters |
|---|---|
| **Hit@1 / Hit@3 / MRR** (in-scope cases) | Is a relevant article at the top? |
| **Precision** of everything shown | Are we cluttering the page with irrelevant articles? |
| **Empty-result rate** (in-scope) | Did a patient with a real, covered symptom get nothing? |
| **False-positive rate** (out-of-scope / no-coverage) | Do we show articles for "my car makes a noise" or for symptoms the library does not cover? |
| **Urgent-warning recall** and **false alarms** | Are emergency and self-harm descriptions always flagged, without alarming people unnecessarily? |
| **Error rate** | Did the pipeline crash? |
| **Latency** (p50 / p95, cold start) | Page responsiveness |
| **Quality (1–10)** | One per-case score from a fixed, deterministic rubric (below) |

**Quality rubric (deterministic, in `ai_services/evaluation.py`):**
- In-scope: 4 points if the top result is relevant, 2 if any of the top 3 is relevant, and 4 × precision.
- Out-of-scope or no-coverage: 10 minus 2 per result shown.
- A red-flag case with no urgent warning is capped at 4.
- A false urgent warning is capped at 7.

**Procedure:** we use 31 labelled development cases across 9 categories: direct, lay language, short/vague, misspelling, multi-symptom, red flag, out of scope, no coverage, and negation. A separate **12-case held-out set** was written *after* tuning and never used to choose thresholds. Every strategy runs the same cases, metrics, and rubric on the same machine (Apple Silicon laptop, CPU). Per-case latency is measured with the model already loaded. Cold start is reported separately.

## 4.2 Realistic tests (final system)

| Test | Input (symptom — description) | Expected behavior | Actual output | Quality (1–10) | Latency |
|---|---|---|---|---|---|
| 1 | "Pounding head" — throbbing on one side, flashing lights before it starts, light makes it worse | Migraine resource at top | **Migraine Basics** (0.57, strong); explanation: "migraines", "throbbing", "one", "side" | 10 | 8.9 ms |
| 2 | "Thirsty all the time" — always thirsty, peeing a lot, vision a little blurry | Diabetes resource | **Diabetes** (0.34, *possible*, distinctive top match) | 10 | 9.3 ms |
| 3 | "Hopeless" — "I have been thinking about ending my life." | Crisis banner with 988 + depression resource | **Crisis banner (988)** + **Depression** | 10 | 9.1 ms |
| 4 | "Chest pain" — crushing pressure spreading to my left arm, sweating | Emergency (911) banner + chest-pain resource | **Emergency banner** + **Chest Pain** (0.58) | 10 | 9.0 ms |
| 5 | "asdfgh" — "qwerty zxcv lorem ipsum" | No recommendations, honest message | **No results**: "We don't have a resource that closely matches…" | 10 | 10.6 ms |
| 6 | "Toothache" — sharp pain in a back molar with cold drinks (no dental article in library) | No recommendations | **Sore Throat** shown as strong match (0.51) ✗ | 8 | 9.1 ms |
| 7 | "Chest tightness" — mild, when anxious, goes away when I relax. "No pain in my arm or jaw." | Anxiety/chest pain resources, **no** emergency banner | Anxiety, Chest Pain ✓, but **false emergency banner** ✗ | 7 | 9.6 ms |
| 8 | Embedding model unavailable (simulated `OSError`) | Page still works with fallback results + notice | Keyword-ranked results with "Keyword match" badge and notice; safety banner still shown | — (unit test) | — |

Aggregate results (31 dev cases): Hit@1 **1.00**, precision **0.96**, urgent recall **1.00**, error rate **0**, mean quality **9.71**, p50 latency **9.0 ms**, p95 **10.6 ms**. Cold start for the first request in a new process is **~2.2 s** (model load). Steady-state requests take **~10 ms**.

## 4.3 Failure analysis

### Failure 1 — Nearest-neighbor false positives for symptoms the library doesn't cover
- **What failed:** "Toothache" was recommended *Sore Throat* (score 0.51, labelled "strong"). On the held-out set, "ear pain + muffled hearing" was recommended *Dizziness and Vertigo*. The false-positive rate on no-match cases is 0.20 (dev) and 0.33 (held-out).
- **Why:** cosine similarity is relative. With 30 articles, the nearest neighbor of an uncovered symptom is often a body-part neighbor (mouth → throat, ear → inner-ear vertigo). The query-cleaning improvement made *all* scores more discriminative, but it also raised this neighbor score above the threshold. Baseline toothache was 0.41 and was filtered out, so this is a real trade-off of the improvement.
- **Impact:** low clinical risk, since the content is educational and the page has a disclaimer. But it is confusing, and labelling the result "strong" overstates confidence.
- **Improvement:** (a) grow the library to cover common gaps such as dental and ear/ENT. (b) Add a cross-encoder re-ranker (e.g., `ms-marco-MiniLM-L-6-v2`) that judges query–article relevance directly instead of distance. (c) Add per-topic calibration or a "body system" classifier that rejects cross-system matches.

### Failure 2 — Safety screen fires on negated red flags
- **What failed:** "Mild chest tightness when I'm anxious… **No pain in my arm or jaw**" triggered the emergency banner.
- **Why:** the cardiac rule fires when chest-pain words appear together with arm/jaw/sweat words. Regexes have no notion of negation scope ("no pain in my arm").
- **Impact:** an unnecessary alarm can frighten the patient and teaches users to ignore warnings. We deliberately accept this direction of error, because a missed emergency is far worse than a false alarm. 1 false alarm in 43 total cases; 0 missed emergencies.
- **Improvement:** add NegEx-style negation detection (ignore a red-flag term when "no / denies / without" occurs within a few words before it), or confirm rule hits with a small NLI model. A clinician should review the rule list.

### Failure 3 — Cold-start latency and an empty, unmigrated database
- **What failed:** the first recommendation in a new server process takes ~2.2 s while torch and the model load, compared with ~10 ms afterwards. On a fresh machine, the first run also downloads ~90 MB. Separately, the repository's committed `db.sqlite3` had not applied migration `0004_educationalresource`, and the library was empty. The original feature therefore could only ever show "couldn't load" or "no resources".
- **Why:** the model is lazy-loaded on first use. Resource embeddings were originally computed one at a time with one `save()` each, on the first request. There was no seed process for the library.
- **Impact:** a slow first page, and a feature that silently did nothing for a new teammate or grader.
- **Improvement (implemented):** `seed_resources --embed` loads the library and pre-computes all embeddings in one batch. Missing embeddings are now computed in a single batched `encode` + `bulk_update`. The README documents `migrate` → `seed_demo`. **Future:** warm the model at worker start (e.g., gunicorn `--preload`).

## 4.4 Improvement: baseline → hybrid ranking

### Before
The original recommender (`--strategy baseline`, preserved in code for reproducibility):
- Built the query from a fixed template that repeated the symptom three times and **always included every field label**, even when empty: `"Frequency: . Duration: . Possible triggers: . Relieving factors: . Question for healthcare provider: . Reported severity: 5 out of 10."`
- Applied one fixed cutoff, cosine ≥ 0.45.
- Had no safety screening.

Baseline testing revealed three in-scope concerns that got **nothing**:

| Case | Correct article's score | Result |
|---|---|---|
| "Feeling down", lost interest, hopeless | Depression 0.448 | nothing (just under 0.45) |
| "Thirsty all the time", peeing a lot, blurry vision | Diabetes 0.375 | nothing |
| "I have been thinking about ending my life." | Depression 0.350 | **nothing, and no crisis message** |

The correct article was always ranked #1. The problem was the threshold and the noisy query, not the model. The empty-field boilerplate made every query look partly alike ("symptom", "healthcare provider", "severity"). That compressed all scores together: gibberish ("asdfgh") still scored 0.27 against medical articles, so a strict cutoff was the only way to keep junk out, and that same cutoff dropped real matches.

### Modification
1. **Clean query construction** (`build_query_text`): only fields the patient filled in, short labels, no severity number.
2. **Confidence-tiered selection** (`hybrid_rank`): strong ≥ 0.45; possible 0.40–0.45; otherwise a lone top match ≥ 0.30 that beats the runner-up by ≥ 0.10.
3. **Red-flag safety screen** before retrieval.
4. Confidence badges and matched-term explanations in the UI.

*Iteration note:* the first version of the modification (strong + distinctive-top-match only) **regressed** one case. "Racing heart and worry" → Anxiety scored 0.434 but led the runner-up by only 0.07, so it returned nothing. Adding the 0.40–0.45 "possible" tier fixed this without adding any false positives. Keeping that intermediate result (`eval_results_hybrid_iter1.json`) shows why each tier exists.

Effect of query cleaning on separation (top score per case):

| | Baseline query | Clean query |
|---|---|---|
| "asdfgh / qwerty" (gibberish) | 0.27 | 0.05 |
| "Car makes a grinding noise" | 0.31 | 0.14 |
| "Dispute an insurance charge" | 0.29 | 0.14 |

### After — development set (31 cases)

| Metric | Baseline | Hybrid iter 1 | **Hybrid (final)** |
|---|---|---|---|
| Hit@1 | 0.885 | 0.962 | **1.000** |
| MRR | 0.885 | 0.962 | **1.000** |
| Precision of shown results | 0.814 | 0.923 | **0.962** |
| Empty results for in-scope concerns | 11.5% | 3.8% | **0%** |
| False-positive rate (no-match cases) | **0.00** | 0.20 | 0.20 |
| Urgent-warning recall | 0.00 | 1.00 | **1.00** |
| Urgent false alarms | 0 | 1 | 1 |
| Mean quality (1–10) | 8.52 | 9.52 | **9.71** |
| Latency p50 / p95 | 8.5 / 10.7 ms | 9.4 / 10.9 ms | 9.0 / 10.6 ms |

### After — held-out set (12 unseen cases, no tuning)

| Metric | Baseline | **Hybrid** |
|---|---|---|
| Hit@1 / MRR | 0.889 | **1.000** |
| Precision | 0.778 | **0.852** |
| Empty results for in-scope concerns | 11.1% | **0%** |
| False-positive rate | 0.33 | 0.33 |
| Urgent-warning recall (stroke signs, "worst headache of my life") | 0.00 | **1.00** |
| Urgent false alarms | 0 | 0 |
| Mean quality | 7.92 | **9.42** |

### Did it work?
**Yes, with one honest trade-off.** Recall and safety improved on both the tuning set and unseen cases. Patients with real, covered symptoms always get a relevant article now, and every emergency or self-harm description is flagged. Before, none were. Quality rose by about 1.2–1.5 points with no meaningful latency cost (under 1 ms). The cost is more nearest-neighbor false positives for uncovered symptoms (Failure 1) and one negation false alarm (Failure 2). Both are documented with concrete next steps.

**Limitations of this evidence:** the evaluation sets are small (43 cases) and were labelled by the team, not clinicians. The thresholds were tuned on the 31 dev cases. The held-out set reduces but does not remove that bias. A larger, clinician-labelled set and real user feedback (e.g., "Was this helpful?" clicks) would be the next step.
