# Care to Share — Evaluation, Deployment & Production Readiness

Part 4 (Evaluation, Testing, and Improvement) and Part 5 (Deployment, Cost, and Production Readiness).

Care to Share has two AI features:

1. **Educational-resource recommender** (`ai_services/resource_recommender.py`). It embeds a patient's health concern with `sentence-transformers/all-MiniLM-L6-v2` and recommends the most semantically similar articles from the `EducationalResource` table. **This is the feature evaluated and improved in Part 4.**
2. **AI pre-visit summary** (`appointments/ai_services.py`). It builds a factual summary from the patient's concerns, then optionally asks a small local LLM (`qwen2.5:0.5b` via Ollama) to suggest clearer wording, which the patient reviews before saving. Part 5 covers its infrastructure, cost, reliability and risks. Its LLM step was not quantitatively evaluated in Part 4 (see Failure 6).

Every number below comes from code in this repository:

```bash
python manage.py seed_resources --embed                     # 30-article MedlinePlus library
python manage.py evaluate_recommender --strategy baseline   # original algorithm
python manage.py evaluate_recommender --strategy improved   # after Part 4.4
python manage.py evaluate_recommender --strategy improved --cases ai_services/data/eval_cases_holdout.json
python manage.py test                                       # 27 tests
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
  - `recommended_resources.html` begins its own `<!DOCTYPE html><html><head><title>` before `{% extends %}`. When the deployed page is opened, the browser tab title shows raw HTML ("<!DOCTYPE html> <html lang= en > …") instead of "Care to Share". The page body renders correctly.
- **Impact:** the feature didn't work out of the box, duplicated code can drift, and the recommendations page looks broken in the tab bar.
- **Fixed / to improve:** `seed_resources --embed` now loads the library, and the build/deploy scripts run `migrate` and the seed automatically. The duplicate definitions and the stray HTML wrapper should be removed by their authors (not changed here, to avoid stepping on teammates' work).

### Failure 5 — Cold-start latency
- **What failed:** the first recommendation in a new process waited ~2.2 s for PyTorch and the model to load, versus ~10 ms afterwards.
- **Fixed (Part 5):** `gunicorn.conf.py` loads the model in `post_worker_init`, so the wait happens at server boot instead of on a user's request. The build step downloads the model and pre-computes article embeddings.

### Failure 6 — The AI summary's wording step depends on a separate Ollama server
- **What failed:** on a fresh deployment without Ollama, clicking **✨ Improve Wording with AI** cannot reach the model. The server logs `ConnectionError: Failed to connect to Ollama`.
- **Why:** `improve_summary_wording()` calls a local Ollama server (`qwen2.5:0.5b`), which is a separate program from Django and pip. The test machine did not have it installed, which is also why this LLM step could not be quantitatively evaluated here.
- **Impact:** limited. The view catches the error and shows "Unable to improve the wording. Please check that Ollama is running.", and the factual summary itself (no LLM) still generates and saves normally. Verified in a browser on 2026-11-17.
- **Could be improved:** `deploy_local.sh` now pulls the model automatically when Ollama is installed and prints a clear notice when it is not. Next steps: add an Ollama container or service to the deployment, show the button only when the model is reachable, and build a faithfulness test set (does the rewrite keep every severity, date and frequency, and add nothing?) to evaluate the LLM the same way the recommender was evaluated.

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

### Deployment approach: reproducible local production deployment

We deliver a **reproducible local deployment**. It runs the same production stack as the cloud configuration on one machine with one command:

```bash
git clone https://github.com/jacquelineshin/Care-to-Share.git
cd Care-to-Share
./deploy_local.sh          # → http://localhost:8000
```

`deploy_local.sh` performs these steps:
1. Creates a virtual environment and installs pinned dependencies.
2. Generates a random `SECRET_KEY`, kept in git-ignored `.env.local`.
3. Sets `DJANGO_DEBUG=False`.
4. Collects static files (served by WhiteNoise) and runs migrations.
5. If Ollama is installed, pulls `qwen2.5:0.5b` for the AI summary's wording step; otherwise prints a notice that this one button will be unavailable.
6. Loads the 30-article library, downloads the embedding model, pre-computes embeddings, and creates the demo account.
7. Starts **gunicorn** with the embedding model pre-loaded.

The only difference from the cloud setup is `DJANGO_HTTPS=False`, because there is no TLS on `localhost`, and SQLite instead of Postgres.

`DJANGO_DEBUG` and `DJANGO_ALLOWED_HOSTS` override the values in `settings.py` only when they are set. A normal developer checkout keeps the team's local defaults (`DEBUG = True`), while the deploy script and `render.yaml` switch to production mode.

### Technical justification for not deploying publicly

1. **The AI model's memory needs exceed every free hosting tier we evaluated.** The gunicorn worker measured **494 MB RSS** with the model loaded, and the install needs ~1 GB of disk (PyTorch alone is 634 MB).
   - Render Free and Starter give 512 MB of RAM, so the worker would be killed for running out of memory. The smallest plan that fits is Standard (2 GB) at $25/month, plus $6/month for Postgres.
   - Hugging Face Spaces has enough RAM (CPU Basic: 2 vCPU / 16 GB), but its documentation now states that Docker and Gradio Spaces "require a paid plan to create" (PRO, $9/month). Its disk is also not persistent, so user data would be lost on every restart.
2. **Privacy.** Care to Share stores personal health information. Putting a public demo with real sign-ups on a free or hobby host, with no data-processing agreement, is not appropriate for this kind of data. A local deployment keeps all data on the operator's machine.
3. **Removing the AI is not an option.** Swapping in a hosted embedding API to fit a 512 MB tier would send symptom text to a third party (see 5.3). Dropping the model would remove the product's core feature.

### Evidence the deployment works

The deployment was verified **from a fresh clone** (no virtual environment, database or model cache), and the primary workflow was run in a browser against the gunicorn server. Results are in "Local deployment verification" below.

### Cloud-ready configuration (not deployed, for cost reasons)

The repository is also ready for a one-click Render Blueprint deploy if the team chooses to pay for it:

| File | Purpose |
|---|---|
| `render.yaml` | Web service (Standard plan) + Postgres database, health check, env vars, generated `SECRET_KEY` |
| `build.sh` | `pip install` → `collectstatic` → `migrate` → `seed_resources --embed` (downloads the model, loads the library, pre-computes embeddings) |
| `gunicorn.conf.py` | 1 worker × 4 threads, model pre-loaded at worker start |
| `requirements.txt` | Pinned versions; **CPU-only PyTorch** wheel (avoids the ~2 GB CUDA build) |
| `config/settings.py` | Configured from environment variables / `.env` (`SECRET_KEY`, `DATABASE_URL`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_HTTPS`); WhiteNoise serves static files |
| `.env.example` | Documents every variable (real `.env` files are git-ignored) |

To deploy on Render: choose **New → Blueprint** and connect this repository. Render reads `render.yaml`, creates the database and web service, runs `build.sh`, and waits for `/healthz/` to pass. Render does not run Ollama, so in that setup the summary's wording button falls back to its error message unless a separate Ollama service is added (see 5.2).

### Local deployment verification

The test was last run on 2026-11-17, against the current `main` including the AI pre-visit summary. It used a fresh `git clone` (no `.venv`, no `db.sqlite3`, empty model cache) and `./deploy_local.sh` on port 8100, on a machine **without** Ollama installed:

| Check | Result |
|---|---|
| Install, migrate, seed, model download | Completed with no manual steps: "Resources created: 30", "Embeddings computed for 30 resources", "Demo user 'demo' ready" |
| Server start | gunicorn worker logged **"Embedding model loaded"** before serving requests |
| `GET /healthz/` | `{"status": "ok", "database": true}` |
| Anonymous `GET /dashboard/` | `302` → `/accounts/login/?next=/dashboard/` |
| Security headers (`DEBUG=False`) | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` |
| **Primary workflow in a browser** | Log in → dashboard → add concern *"Can't sleep — I lie awake until 3am most nights and feel exhausted at work"* (severity 6) → concern saved → **Find Educational Resources** → *Insomnia and Trouble Sleeping* (0.583), *Fatigue* (0.462) |
| AI pre-visit summary | **Generate Summary** → "Your AI summary draft is ready" with the factual summary. **✨ Improve Wording with AI** (no Ollama) → friendly message "Unable to improve the wording. Please check that Ollama is running.", HTTP 200, no crash |
| Monitoring log | `ai.recommend concern=1 results=2 latency_ms=23.5`. Symptom text appears **0 times** in the server log (also checked after the summary requests) |
| `manage.py check --deploy` (cloud settings) | Only `SECURE_HSTS_PRELOAD` remains (intentionally off; preload is hard to undo) |

## 5.2 Infrastructure requirements

Measured on the production-mode run:

| Resource | Requirement | Evidence / reasoning |
|---|---|---|
| **CPU** | 1 vCPU is enough at class/pilot scale | One thread: **136 recommendations/s**, p50 6.3 ms, p95 7.5 ms; one embedding ≈ 3.8 ms (`torch.set_num_threads(1)`) |
| **GPU** | **Not needed** | 22M-parameter model; CPU inference is milliseconds |
| **RAM** | **~500 MB per worker process**; plan for 2 GB | Gunicorn worker RSS after loading the model: **494 MB**; master: 28 MB. Render's 512 MB Starter plan would run out of memory, hence the Standard (2 GB) plan |
| **Storage** | ~1 GB for the environment | PyTorch 634 MB, model ~90 MB, whole venv 1.2 GB (Linux CPU wheels are smaller than macOS) |
| **Database** | Managed Postgres; tiny | 30 articles × 384-float embeddings ≈ 0.3 MB; user data is text rows. Smallest Render Postgres (256 MB) is plenty |
| **AI inference (recommender)** | In-process, same container as Django | No separate model server at this scale; the model is loaded once per worker |
| **AI inference (summary wording)** | A separate **Ollama** server on the same machine, CPU only | Model `qwen2.5:0.5b`: 494M parameters, Q4_K_M quantized, **398 MB download** (Ollama library page). Expect roughly that much extra RAM plus runtime overhead; **not measured here** because Ollama was not installed on the test machine. Generating ~350 tokens on CPU takes seconds, not milliseconds |

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

**The AI summary's LLM follows the same trade-off.** Today it runs locally through Ollama, so patient text again stays on our machine and there is no per-token cost. In the cloud it would need roughly another 0.5–1 GB of RAM (Render Pro, $85/month, instead of Standard) or its own small instance. The hosted alternative is a chat-completion API, which charges per token and sends symptom text to a third party.

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

**Primary bottleneck:** two different limits, one per AI feature.
- **LLM wording step (CPU):** each "Improve Wording" request generates up to 350 tokens with a 0.5B model, which takes seconds of CPU instead of milliseconds. Even a few hundred requests per peak hour would queue behind each other on one Ollama server. It needs its own inference server(s), a request queue, and a per-user rate limit.
- **Recommender (memory, not CPU):** Peak AI load (~1.3–7 req/s) is far below one thread's measured 136 req/s, but every worker process holds a ~500 MB copy of PyTorch and the model. Memory therefore caps how many processes fit on each instance. Next comes the database: `recommend_resources` loads every article's embedding from the database and compares them in a Python loop. That is fine for 30 articles, but it grows linearly with the library.

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
2. **Separate inference services:** a shared embedding service (or ONNX Runtime) so web workers don't each carry a model, and one or more dedicated **Ollama/LLM servers** behind a queue for the summary wording step. Several web processes would then share one model server.
3. **A background job queue** (Celery/RQ) for re-embedding the library when articles change.
4. **Redis** for cache and rate limits shared across instances.

## 5.5 Security and reliability

| Area | What is implemented | Where |
|---|---|---|
| **Environment variables** | `SECRET_KEY` comes from the environment or a git-ignored `.env` file; the app **refuses to start** without it, and the old hard-coded key is gone. `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`, `DJANGO_HTTPS` and rate limits are environment-driven. Render and `deploy_local.sh` generate the secret automatically | `config/settings.py`, `render.yaml`, `.env.example`, `.gitignore` |
| **Input validation** | Django forms validate symptom length, severity 1–10, dates and choices. The recommender ignores empty descriptions and caps query text at 3,000 characters | `appointments/forms.py`, `resource_recommender.py` |
| **Authentication & permissions** | Every patient page is `@login_required`. All queries are filtered by `user=request.user`, so another user's concern returns 404 (tested). Password validators are on. Sessions expire after 8 hours. Repeated failed logins trigger a temporary lockout (see Rate limiting) | `views.py`, `settings.py`, tests |
| **API key protection** | Both AI models run locally (sentence-transformers in-process, Ollama on localhost), so there are **no API keys to leak**. The `openai` package is installed only because the summary view imports its error class; no OpenAI key is configured. A hosted API's key would live only in an environment variable | design |
| **Transport & headers** | With `DEBUG=False`: HTTPS redirect, secure + HttpOnly cookies, HSTS (30 days), nosniff, `X-Frame-Options: DENY`, same-origin referrer policy, CSRF trusted origins | `settings.py` |
| **Error handling** | The recommendation view catches model and database errors and shows "We couldn't load educational resources right now" with HTTP 200 (tested with a simulated crash). `/healthz/` returns 503 if the DB is down. A model warm-up failure doesn't stop the server. The AI summary view catches LLM failures and shows "Unable to improve the wording…" (verified without Ollama) | `views.py`, `ai_services/health.py`, `gunicorn.conf.py` |
| **Rate limiting** | **AI endpoint:** 20 recommendation requests per user per minute (configurable). Over the limit returns **HTTP 429** with `Retry-After: 60` and a friendly page (tested). **Login (brute-force protection):** after **5 failed attempts for the same username *or* from the same IP within 5 minutes**, logins are refused with HTTP 429 and "Too many failed login attempts. Please wait 5 minutes", even if the next password is correct. The username check is case-insensitive, and a successful login clears that username's counter. Verified in a browser: 5 failures → 6th request 429. 8 tests | `ai_services/ratelimit.py`, `config/login_throttle.py` |
| **Logging & monitoring** | Logs go to stdout and are collected by Render. Each AI call logs `concern id, result count, latency_ms`. Failed and blocked logins log `login.failed` / `login.locked` with the IP only; usernames are hashed, never logged. Access log via gunicorn. Render health check on `/healthz/` | `settings.LOGGING`, `views.py` |
| **User privacy** | **Patient text is never logged** (only ids, counts and latency) and is never sent to a third party (local model). The database is managed Postgres with encryption at rest provided by the host | design, `views.py` |
| **AI-related risks** | **Recommender:** only vetted MedlinePlus articles can be shown, so it generates no medical text. **Summary LLM:** the prompt forbids inventing symptoms, changing severities or dates, diagnosing or advising, and treats input as data. Patient questions are left out of the request, temperature is 0, the factual summary is never overwritten, and the patient must review the suggestion before saving. A 0.5B model can still miss these rules, so the human review step matters. A disclaimer on the page says the content is educational, not diagnostic. Uncovered symptoms can still get a loosely related article (Failure 2), and there is **no emergency detection yet** (Failure 3). This is the most important remaining risk, with a concrete fix proposed | template, 4.3 |

**Not yet done (honest gaps):** emergency/red-flag detection (Failure 3), a rate limit and faithfulness evaluation for the LLM wording step (Failure 6), a shared Redis cache for rate limits across multiple instances, an error-tracking service (e.g., Sentry), login throttling on the Django admin login (`/admin/login/` still uses the default view), and a formal HIPAA review before handling real patient data.
