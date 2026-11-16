# Care to Share — Evaluation, Deployment & Production Readiness

Part 4 (Evaluation, Testing, and Improvement) and Part 5 (Deployment, Cost, and Production Readiness).

The AI feature evaluated here is the **educational-resource recommender** (`ai_services/resource_recommender.py`). It embeds a patient's health concern with `sentence-transformers/all-MiniLM-L6-v2` and recommends the most semantically similar articles from the `EducationalResource` table.

Every number below comes from code in this repository:

```bash
python manage.py seed_resources --embed                     # 30-article MedlinePlus library
python manage.py evaluate_recommender --strategy baseline   # original algorithm
python manage.py evaluate_recommender --strategy improved   # after Part 4.4
python manage.py evaluate_recommender --strategy improved --cases ai_services/data/eval_cases_holdout.json
python manage.py test                                       # 19 tests
```

Raw per-case results: `ai_services/data/eval_results_{baseline,improved}[_holdout].json`.

---

# Part 4 — Evaluation, Testing, and Improvement

## 4.1 Evaluation criteria

Patients describe symptoms in their own words, and the app should point them to a relevant, trustworthy article or honestly say it has none. We chose these metrics:

| Metric | What it measures | Why it matters for Care to Share |
|---|---|---|
| **Hit@1** | Top recommendation is relevant | Most users read only the first card |
| **Hit@3 / MRR** | Rank of the first relevant article | Retrieval relevance |
| **Precision** | Share of shown articles that are relevant | Irrelevant medical reading confuses patients |
| **Empty-result rate** (in-scope) | Patient with a covered symptom gets nothing | The feature silently fails for them |
| **False-positive rate** (no-match cases) | Articles shown for gibberish, non-medical, or uncovered symptoms | Honest "no match" beats a wrong match |
| **Error rate** | Pipeline raised an exception | Reliability |
| **Latency** (p50/p95; model load) | Time inside `recommend_resources` | Page responsiveness |
| **Quality (1–10)** | Deterministic per-case rubric | Single comparable score |

**Quality rubric** (`ai_services/evaluation.py → quality_score`):
- In-scope cases: 4 points if the top result is relevant, 2 if any of the top 3 is relevant, and 4 × precision. No results scores 1.
- No-match cases: 10 minus 2 per result shown.
- Pipeline error: 1.

**Consistent procedure:**
- **Development set:** 31 labelled cases in `eval_cases.json`, across 9 categories: direct, lay language, short/vague, misspelling, multi-symptom, red flag, out-of-scope, not covered by the library, and negation.
- **Held-out set:** 12 cases in `eval_cases_holdout.json`, written after the improvement was tuned and never used to choose thresholds.
- Each case lists the article topics a reviewer judged relevant.
- Every strategy runs the same cases, metrics, rubric and database, on the same machine (Apple Silicon laptop, CPU).
- Latency is measured per call with the model already loaded. Model loading is reported separately.

## 4.2 Realistic tests

Final (improved) system. The "Before" column shows the original algorithm's output on the same input.

| Test | Input (symptom — description) | Expected behavior | Actual output (after) | Before | Quality (1–10) | Latency |
|---|---|---|---|---|---|---|
| 1 | "Pounding head" — throbbing on one side, flashing lights before it starts, light makes it worse | Migraine article first | Migraine Basics (0.57) | Migraine, Headache | 10 | 10.3 ms |
| 2 | "Feeling down" — lost interest in things I used to enjoy, hopeless most days | Depression article | Depression (0.47) | **nothing** (Q = 1) | 10 | 9.0 ms |
| 3 | "Thirsty all the time" — always thirsty, peeing a lot, vision a little blurry | Diabetes article | Diabetes (0.34) | **nothing** (Q = 1) | 10 | 9.3 ms |
| 4 | "Chest pain" — crushing pressure spreading to my left arm, sweating | Chest-pain article (ideally an emergency warning too) | Chest Pain (0.58), no urgent warning | Chest Pain | 10* | 9.3 ms |
| 5 | "asdfgh" — "qwerty zxcv lorem ipsum" | No recommendations | No recommendations | No recommendations | 10 | 9.2 ms |
| 6 | "Toothache" — sharp pain in a back molar with cold drinks (no dental article exists) | No recommendations | **Sore Throat (0.51)** ✗ | No recommendations | 8 | 8.8 ms |
| 7 | "Hopeless" — "I have been thinking about ending my life." | Depression article + crisis help | Depression (0.32), no crisis message | **nothing** (Q = 1) | 10* | 9.1 ms |

\* The rubric scores retrieval only. Tests 4 and 7 show a product limitation the rubric does not capture: there is no urgent-care message (see Failure 3).

**Summary (31 development cases):**

| | Before | After |
|---|---|---|
| Hit@1 | 0.885 | **1.000** |
| Precision | 0.814 | **0.962** |
| In-scope empty-result rate | 11.5% | **0%** |
| False-positive rate | **0%** | 20% |
| Error rate | 0 | 0 |
| Mean quality | 8.90 | **9.81** |
| p50 / p95 latency | 9.0 / 11.3 ms | 9.3 / 10.3 ms |

## 4.3 Failure analysis

### Failure 1 — Patients with real, covered symptoms got no recommendations (original system)
- **What failed:** "Feeling down / hopeless", "always thirsty, peeing a lot" and "thinking about ending my life" returned **zero** articles. The library does contain Depression and Diabetes articles. That is 3 of 26 in-scope cases (11.5%), plus "Stressed / Overwhelmed" (1 of 9) on the held-out set.
- **Why:** inspecting the raw scores showed the correct article was **always ranked #1**. Its score was just below the single fixed cutoff of 0.45 (0.448, 0.375, 0.350). The cutoff had to be strict because `build_concern_text()` stuffed every query with the same boilerplate: the symptom repeated three times and labels for empty fields ("Possible triggers: . Relieving factors: . Question for healthcare provider: . Reported severity: 5 out of 10"). That shared text pushed all scores together, so even gibberish scored 0.27 against medical articles.
- **Impact:** the patients with the vaguest, most emotional, or most serious descriptions got the empty "check back later" message, and the self-harm case got no help at all.
- **Improvement:** implemented in 4.4.

### Failure 2 — Uncovered symptoms get the "nearest" article (after the improvement)
- **What failed:** "Toothache" → *Sore Throat* (0.51). Held-out "ear pain, muffled hearing" → *Dizziness and Vertigo* (0.41). The false-positive rate on no-match cases rose from 0% to 20% on the development set, and stayed at 33% on the held-out set (the case that fails changed).
- **Why:** cosine similarity only ranks. With 30 articles, the closest one to an uncovered complaint is often a neighbouring body part (mouth → throat, ear → inner ear). Cleaning the query made scores more spread out overall, and this pushed the toothache neighbour above 0.45. This is a real trade-off of the improvement.
- **Impact:** low clinical risk, since the articles are educational and carry a disclaimer. But it is confusing and erodes trust.
- **Could be improved:** add articles for common gaps (dental, ear/ENT, hair/skin). Add a cross-encoder re-ranker (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) that scores query–article relevance directly. Or reject matches whose body system differs from the query's.

### Failure 3 — Red-flag symptoms get only reading material
- **What failed:** "Crushing chest pressure spreading to my left arm" and "thinking about ending my life" receive an article but no "call 911 / 988" message.
- **Why:** the recommender only does retrieval. Nothing in the app classifies urgency.
- **Impact:** potentially serious. A patient describing a heart attack or suicidal thoughts should be told to seek help now, not read an article before next week's appointment.
- **Could be improved:** add a rule-based red-flag screen (chest pain + arm/jaw/sweating, can't breathe, stroke signs, self-harm language) that runs before retrieval and shows an emergency or 988 banner. It should handle negation ("no pain in my arm"), and a clinician should review the rules.

### Failure 4 — Django and data issues found while testing
- **What failed:**
  - The originally committed `db.sqlite3` had not applied migration `0004_educationalresource`, and the library was empty. The feature could only show "couldn't load" or "no resources" for a new teammate or grader.
  - `appointments/models.py` defines `VisitResponse` twice, and `appointments/views.py` defines `visit_companion` twice. Django prints `RuntimeWarning: Model 'appointments.visitresponse' was already registered`, and the second definitions silently replace the first.
- **Impact:** the feature didn't work out of the box, and duplicated code can drift.
- **Fixed / to improve:** `seed_resources --embed` now loads the library, and the build script runs `migrate` and the seed automatically on every deploy. The duplicate definitions should be removed by the visit-companion author (not changed here, to avoid stepping on a teammate's work).

### Failure 5 — Cold-start latency
- **What failed:** the first recommendation in a new process waited ~2.2 s for PyTorch and the model to load, versus ~10 ms afterwards.
- **Fixed (Part 5):** `gunicorn.conf.py` loads the model in `post_worker_init`, so the wait happens at server boot instead of on a user's request. The build step downloads the model and pre-computes article embeddings.

## 4.4 Improvement

### Before
- The query was `build_concern_text()`: symptom ×3 plus every label, even empty ones.
- Results were filtered by a single threshold, ≥ 0.45.
- Measured on the development set: Hit@1 0.885, empty-result rate 11.5%, quality 8.90.

### Modification (`ai_services/resource_recommender.py`)
1. **`build_query_text()`** uses only the fields the patient filled in, with short labels and the frequency shown as a readable label. Severity numbers are dropped because they carry no topical meaning.
2. **`select_recommendations()`** replaces the single cutoff with confidence tiers:
   - show every article ≥ 0.45 ("strong");
   - else show articles from 0.40 to 0.45 ("possible");
   - else show the single best article if it scores ≥ 0.30 **and** beats the runner-up by ≥ 0.10 (a clearly separated match);
   - else show nothing.
3. The original algorithm is preserved as `recommend_resources(..., strategy="baseline")` so before/after can be reproduced. Tests cover both paths.

Why the cleaned query helps: the top similarity scores for no-match inputs dropped sharply, which separated junk from real symptoms.

| Input | Original query | Cleaned query |
|---|---|---|
| "asdfgh / qwerty zxcv" | 0.27 | 0.05 |
| "My car makes a grinding noise" | 0.31 | 0.14 |
| "Dispute a charge on my insurance bill" | 0.29 | 0.14 |

### After

| Metric | Before (dev) | **After (dev)** | Before (held-out) | **After (held-out)** |
|---|---|---|---|---|
| Hit@1 / MRR | 0.885 | **1.000** | 0.889 | **1.000** |
| Precision | 0.814 | **0.962** | 0.778 | **0.852** |
| In-scope empty-result rate | 11.5% | **0%** | 11.1% | **0%** |
| False-positive rate | **0%** | 20% | 33% | 33% |
| Mean quality (1–10) | 8.90 | **9.81** | 8.75 | **9.42** |
| p50 latency | 9.0 ms | 9.3 ms | 9.1 ms | 10.0 ms |

**Did it work?** Yes. Every in-scope patient now gets a relevant top article, on the tuning set and on the 12 unseen held-out cases. Mean quality improved by 0.9 (dev) and 0.7 (held-out), with no measurable latency cost. The trade-off is Failure 2: one extra false positive on the dev set for a symptom the library doesn't cover.

**Limits of the evidence:** 43 team-labelled cases, not clinician-labelled. The thresholds were tuned on the dev set; the held-out set reduces but does not remove that bias. Next steps would be a larger labelled set and in-app "Was this helpful?" feedback.

---

# Part 5 — Deployment, Cost, and Production Readiness

## 5.1 Deployment

**Target platform: Render** (managed Python web service + managed Postgres). The repo now contains everything needed for a one-click Blueprint deploy:

| File | Purpose |
|---|---|
| `render.yaml` | Web service (Standard plan) + Postgres database, health check, env vars, generated `DJANGO_SECRET_KEY` |
| `build.sh` | `pip install` → `collectstatic` → `migrate` → `seed_resources --embed` (downloads the model, loads the library, pre-computes embeddings) |
| `gunicorn.conf.py` | 1 worker × 4 threads, model pre-loaded at worker start |
| `requirements.txt` | Pinned versions; **CPU-only PyTorch** wheel (avoids the ~2 GB CUDA build) |
| `config/settings.py` | Configured from environment variables (`DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`); WhiteNoise serves static files |
| `.env.example` | Documents every variable (real `.env` files are git-ignored) |

**Deploy steps:**
1. In Render, choose **New → Blueprint** and connect this GitHub repository. Render reads `render.yaml`, creates the database and web service, and runs `build.sh`.
2. Wait for the `/healthz/` check to go green.
3. Open the site, register an account, and create an appointment and a health concern. Then click **Find Educational Resources** to exercise the primary AI workflow.

**Deployed URL:** _add after deploying_.

**Verified locally in production mode**, with `DJANGO_DEBUG=False`, a random secret key, gunicorn, and collected static files:
- `/healthz/` returned `{"status": "ok", "database": true}`.
- The login page returned 200.
- WhiteNoise served `style.css` (200).
- `/dashboard/` redirected anonymous users to login (302).
- The worker logged "Embedding model loaded" at boot.
- `manage.py check --deploy` reports only `SECURE_HSTS_PRELOAD` (intentionally off; preload is hard to undo).

## 5.2 Infrastructure requirements

Measured on the production-mode run:

| Resource | Requirement | Evidence / reasoning |
|---|---|---|
| **CPU** | 1 vCPU is enough at class/pilot scale | One thread: **136 recommendations/s**, p50 6.3 ms, p95 7.5 ms; one embedding ≈ 3.8 ms (`torch.set_num_threads(1)`) |
| **GPU** | **Not needed** | 22M-parameter model; CPU inference is milliseconds |
| **RAM** | **~500 MB per worker process**; plan for 2 GB | Gunicorn worker RSS after loading the model: **494 MB**; master: 28 MB. Render's 512 MB Starter plan would run out of memory, hence the Standard (2 GB) plan |
| **Storage** | ~1 GB for the environment | PyTorch 634 MB, model ~90 MB, whole venv 1.2 GB (Linux CPU wheels are smaller than macOS) |
| **Database** | Managed Postgres; tiny | 30 articles × 384-float embeddings ≈ 0.3 MB; user data is text rows. Smallest Render Postgres (256 MB) is plenty |
| **AI inference** | In-process, same container as Django | No separate model server at this scale; the model is loaded once per worker |

## 5.3 Cost comparison

Prices checked November 2026 on Render's pricing page and OpenAI's model page.

**A. Self-hosted model (current design)** — MiniLM runs inside the Django container.
**B. Hosted embedding API** — replace MiniLM with OpenAI `text-embedding-3-small` ($0.02 per 1M tokens). Django no longer needs PyTorch.

| Factor | A. Self-hosted MiniLM | B. Hosted embedding API |
|---|---|---|
| Hardware | 2 GB RAM web instance (model + PyTorch ≈ 500 MB) | 512 MB instance is enough (no PyTorch) |
| Monthly cost, pilot | Render Standard **$25** + Postgres **$6** = **~$31** | Render Starter **$7** + Postgres **$6** + API ≈ **$0.01** = **~$13** |
| Monthly cost, 10k DAU (assumptions in 5.4) | 2 × Pro (4 GB/2 CPU) **$170** + Postgres 1 GB **$19** + Redis = **~$200** | 2 × Standard **$50** + Postgres **$19** + Redis + API ≈ **$1/month** = **~$80** |
| Latency per query | ~4–10 ms, in-process | Adds a network round-trip to the API on every request; depends on region and API load |
| Maintenance | We pin and upgrade PyTorch and the model, manage RAM, and handle cold starts | Minimal: an API key, retry/backoff, and watching for model deprecations (a model change means re-embedding the library) |
| Scalability | Scale by adding RAM-heavy instances; each process needs its own model copy | The provider scales inference; we only scale lightweight web instances |
| Reliability | No external dependency; works offline | Outages and rate limits from the provider become our outages; needs a fallback |
| Privacy | **Symptom text never leaves our servers** | Patient symptom text is sent to a third party. Health data would need a vendor agreement (e.g., a HIPAA BAA) and a data-retention review |

**Recommendation:** keep **A (self-hosted)**. The hosted API is cheaper in dollars because embeddings cost almost nothing. But Care to Share handles personal health information, and privacy plus no external dependency are worth roughly $18/month at pilot scale. If cost became critical, a middle option is **ONNX Runtime** instead of PyTorch. That keeps the same model local while shrinking RAM to fit cheaper instances; we have not measured this.

## 5.4 Scalability to 10,000 daily active users

**Assumptions:**
- 10,000 DAU, ~20 page views per user per day, so 200k requests/day.
- ~3 recommendation requests per user per day, so 30k AI calls/day.
- The busiest hour carries 15% of traffic: ~8 page requests/s and ~1.3 AI requests/s at peak, with bursts at maybe 5× that.
- ~60 tokens per embedded query.

**Infrastructure required:**
- **2 web instances** (Render Pro, 4 GB / 2 CPU each) behind Render's load balancer, for redundancy and zero-downtime deploys. Each runs 2 gunicorn workers × 4 threads.
- **Managed Postgres** (Basic 1 GB) with daily backups. SQLite cannot be shared between instances.
- **Redis** (Render Key Value) for a shared cache and shared rate-limit counters. The current `LocMemCache` is per-process.
- Static files stay on WhiteNoise. A CDN in front is optional.

**Primary bottleneck:** **memory, not CPU.** Peak AI load (~1.3–7 req/s) is far below one thread's measured 136 req/s, but every worker process holds a ~500 MB copy of PyTorch and the model. Memory therefore caps how many processes fit on each instance. Next comes the database: `recommend_resources` loads every article's embedding from the database and compares them in a Python loop. That is fine for 30 articles, but it grows linearly with the library.

**How AI inference cost changes:**
- Self-hosted: cost scales with **instances, not requests**. Going from pilot to 10k DAU roughly moves from ~$31 to ~$200/month, mostly for RAM.
- Hosted API: 30k queries × 60 tokens ≈ 1.8M tokens/day ≈ 54M tokens/month ≈ **$1.08/month**. API spend stays negligible even at 10× this traffic; the cost would be privacy and dependency, not money.

**Maintaining performance:**
- Keep the model pre-loaded at worker start (implemented).
- Cache recommendations per concern, invalidated when the concern is edited, since the same concern is often viewed repeatedly.
- Vectorise the similarity step: one NumPy matrix multiply instead of a Python loop.
- Monitor p95 latency and memory per instance, and autoscale on memory.

**Architectural improvements needed:**
1. **pgvector** in Postgres (or FAISS) to store embeddings and do nearest-neighbour search in the database once the library grows to thousands of articles.
2. **A separate inference service** (or ONNX Runtime) so web workers don't each carry a model. Several web processes would then share one model server.
3. **A background job queue** (Celery/RQ) for re-embedding the library when articles change.
4. **Redis** for cache and rate limits shared across instances.

## 5.5 Security and reliability

| Area | What is implemented | Where |
|---|---|---|
| **Environment variables** | Secret key, debug flag, hosts, DB URL and rate limit come from the environment. The app **refuses to start** with `DEBUG=False` and no secret key. The old hard-coded key is gone. Render generates the secret | `config/settings.py`, `render.yaml`, `.env.example`, `.gitignore` |
| **Input validation** | Django forms validate symptom length, severity 1–10, dates and choices. The recommender ignores empty descriptions and caps query text at 3,000 characters | `appointments/forms.py`, `resource_recommender.py` |
| **Authentication & permissions** | Every patient page is `@login_required`. All queries are filtered by `user=request.user`, so another user's concern returns 404 (tested). Password validators are on. Sessions expire after 8 hours | `views.py`, `settings.py`, tests |
| **API key protection** | The AI model is local, so there are **no API keys to leak**. If option B were adopted, the key would live only in an environment variable | design |
| **Transport & headers** | With `DEBUG=False`: HTTPS redirect, secure + HttpOnly cookies, HSTS (30 days), nosniff, `X-Frame-Options: DENY`, same-origin referrer policy, CSRF trusted origins | `settings.py` |
| **Error handling** | The recommendation view catches model and database errors and shows "We couldn't load educational resources right now" with HTTP 200 (tested with a simulated crash). `/healthz/` returns 503 if the DB is down. A model warm-up failure doesn't stop the server | `views.py`, `ai_services/health.py`, `gunicorn.conf.py` |
| **Rate limiting** | 20 AI recommendation requests per user per minute (configurable). Over the limit returns **HTTP 429** with `Retry-After: 60` and a friendly page (tested) | `ai_services/ratelimit.py` |
| **Logging & monitoring** | Logs go to stdout and are collected by Render. Each AI call logs `concern id, result count, latency_ms`. Access log via gunicorn. Render health check on `/healthz/` | `settings.LOGGING`, `views.py` |
| **User privacy** | **Patient text is never logged** (only ids, counts and latency) and is never sent to a third party (local model). The database is managed Postgres with encryption at rest provided by the host | design, `views.py` |
| **AI-related risks** | Only vetted MedlinePlus articles can be shown, so there is no generated medical text and no hallucinated advice. A disclaimer on the page says the content is educational, not diagnostic. Uncovered symptoms can still get a loosely related article (Failure 2), and there is **no emergency detection yet** (Failure 3). This is the most important remaining risk, with a concrete fix proposed | template, 4.3 |

**Not yet done (honest gaps):** emergency/red-flag detection (Failure 3), a shared Redis cache for rate limits across multiple instances, an error-tracking service (e.g., Sentry), account lockout after repeated failed logins, and a formal HIPAA review before handling real patient data.
