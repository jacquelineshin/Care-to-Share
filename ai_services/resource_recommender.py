"""
Educational-resource recommender for Care to Share.

Pipeline (see AI_REPORT.md for the full write-up):

    HealthConcern (DB) -> validation -> red-flag safety screen
    -> query text construction -> MiniLM sentence embedding
    -> cosine similarity against cached resource embeddings (DB)
    -> confidence-aware thresholding -> explanation (matched terms)
    -> RecommendationResult -> Django template

Two ranking strategies are kept so the improvement can be reproduced:

* ``baseline`` - the original implementation: a templated query that
  repeats the symptom and always includes every field label, filtered
  by a single fixed cosine threshold (0.45).
* ``hybrid``   - the improved implementation: query built only from
  fields the patient filled in, a strong threshold plus a
  "distinctive top match" rule for lower-scoring but clearly separated
  matches, and confidence labels shown to the user.

If the embedding model cannot be loaded or fails at inference time, the
recommender degrades to a transparent keyword-overlap ranker instead of
erroring, and tells the user it did so.
"""

import logging
import math
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache

from appointments.models import EducationalResource
from ai_services.safety import screen_concern


logger = logging.getLogger(__name__)


# Lightweight semantic-search model (22M parameters, 384-dim output).
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
MAX_TEXT_CHARS = 3000

# Baseline settings (original implementation).
BASELINE_MIN_SCORE = 0.45

# Hybrid settings, chosen from the evaluation in AI_REPORT.md.
STRONG_MATCH = 0.45        # results at/above this are "strong" matches
POSSIBLE_MATCH = 0.40      # 0.40-0.45 band is shown as "possible" matches
POSSIBLE_MATCH_FLOOR = 0.30  # a lone top result may be shown above this...
DISTINCT_MARGIN = 0.10     # ...if it beats the runner-up by this much
MIN_MEANINGFUL_CHARS = 3

# Result statuses
OK = "ok"
NO_MATCH = "no_match"
INSUFFICIENT_INPUT = "insufficient_input"
FALLBACK = "fallback"
ERROR = "error"


class EmbeddingError(RuntimeError):
    """Raised when the model is unavailable or returns an invalid vector."""


@dataclass
class RecommendationResult:
    recommendations: list = field(default_factory=list)
    status: str = OK
    message: str = ""
    safety_alert: object = None
    strategy: str = "hybrid"
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Model access
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_embedding_model():
    """
    Load the embedding model once per process and reuse it.
    CPU is used so the app runs on machines without a compatible GPU.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, device="cpu")


def _validate_vector(vector):
    if (
        not isinstance(vector, list)
        or len(vector) != EMBEDDING_DIM
        or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector)
    ):
        raise EmbeddingError("Model returned an invalid embedding.")
    return vector


def encode_texts(texts):
    """
    Embed a batch of texts. Returns a list of normalized vectors.
    Any failure (missing package, failed download, bad output) is
    converted into EmbeddingError so callers can fall back cleanly.
    """
    try:
        model = get_embedding_model()
        vectors = model.encode(
            list(texts),
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        vectors = [v.tolist() for v in vectors]
    except EmbeddingError:
        raise
    except Exception as exc:  # noqa: BLE001 - any model failure is handled
        raise EmbeddingError(str(exc)) from exc

    return [_validate_vector(v) for v in vectors]


def create_embedding(text):
    """Convert one text into a normalized embedding (kept for baseline)."""
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


# ---------------------------------------------------------------------------
# Text construction
# ---------------------------------------------------------------------------

def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_concern_text(concern):
    """
    BASELINE query text: repeats the primary symptom and always includes
    every field label, even when the field is empty.
    """

    symptom = str(concern.symptom or "").strip()
    description = str(concern.description or "").strip()
    frequency = str(concern.frequency or "").strip()
    duration = str(concern.duration or "").strip()
    triggers = str(concern.triggers or "").strip()
    relieving_factors = str(concern.relieving_factors or "").strip()
    question = str(concern.question_for_doctor or "").strip()

    parts = [
        f"Primary health concern: {symptom}.",
        f"Main symptom: {symptom}.",
        f"Reported symptom: {symptom}.",
        f"Additional description: {description}.",
        f"Frequency: {frequency}.",
        f"Duration: {duration}.",
        f"Possible triggers: {triggers}.",
        f"Relieving factors: {relieving_factors}.",
        f"Question for healthcare provider: {question}.",
        f"Reported severity: {concern.severity} out of 10."
    ]

    return " ".join(
        part for part in parts if part.strip()
    )[:MAX_TEXT_CHARS]


def build_query_text(concern):
    """
    HYBRID query text: only fields the patient actually filled in, with
    short natural-language labels. Severity is left out because a number
    carries no topical meaning for the embedding model.
    """
    frequency = (
        concern.get_frequency_display()
        if getattr(concern, "frequency", "") else ""
    )

    labelled = [
        ("", concern.symptom),
        ("", concern.description),
        ("Happens", frequency),
        ("Lasts", concern.duration),
        ("Worse with", concern.triggers),
        ("Better with", concern.relieving_factors),
        ("Question", concern.question_for_doctor),
    ]

    parts = []
    for label, value in labelled:
        value = _clean(value)
        if value:
            parts.append(f"{label}: {value}" if label else value)

    return ". ".join(parts)[:MAX_TEXT_CHARS]


def build_resource_text(resource):
    """
    Combine an educational resource's information
    into text that the model can compare with a concern.
    """
    parts = [
        resource.title,
        resource.description,
        resource.topic,
        resource.content,
    ]

    return " ".join(
        str(part).strip()
        for part in parts
        if part and str(part).strip()
    )[:MAX_TEXT_CHARS]


# ---------------------------------------------------------------------------
# Resource embeddings (stored in the database)
# ---------------------------------------------------------------------------

def _stored_embedding_is_valid(embedding):
    try:
        _validate_vector(embedding)
        return True
    except EmbeddingError:
        return False


def get_resource_embedding(resource):
    """
    BASELINE helper: reuse a stored embedding or compute and save one.
    """
    embedding = resource.embedding

    if isinstance(embedding, list) and len(embedding) == EMBEDDING_DIM:
        return embedding

    resource_text = build_resource_text(resource)

    if not resource_text.strip():
        return None

    embedding = create_embedding(resource_text)

    resource.embedding = embedding
    resource.save(update_fields=["embedding"])

    return embedding


def load_resource_embeddings():
    """
    Return [(resource, embedding)] for every usable resource. Missing or
    corrupted embeddings are recomputed in one batch and saved, so the
    first request after seeding does one model call instead of N.
    """
    resources = list(EducationalResource.objects.exclude(content=""))

    stale = [r for r in resources if not _stored_embedding_is_valid(r.embedding)]

    if stale:
        texts = [build_resource_text(r) for r in stale]
        vectors = encode_texts(texts)

        for resource, vector in zip(stale, vectors):
            resource.embedding = vector

        EducationalResource.objects.bulk_update(stale, ["embedding"])

    return [(r, r.embedding) for r in resources]


def refresh_embeddings():
    """Recompute embeddings for all resources (management command helper)."""
    EducationalResource.objects.update(embedding=None)
    return len(load_resource_embeddings())


# ---------------------------------------------------------------------------
# Explanation and keyword fallback
# ---------------------------------------------------------------------------

STOPWORDS = set("""
a about after again all also am an and any are as at be been before being
but by can could did do does doing for from had has have having he her his
how i if in into is it its just like me more most my no not now of off on
once only or other our out over own same she so some such than that the
their them then there these they this those through to too under until up
very was we were what when where which while who why will with would you
your feel feels feeling felt get gets got really lot lots day days week
weeks month months time times thing things going went bit little keep since
""".split())


def _stem(word):
    for suffix in ("ing", "es", "s", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokenize(text):
    words = re.findall(r"[a-z]+", str(text or "").lower())
    return {_stem(w) for w in words if len(w) > 2 and w not in STOPWORDS}


def matched_terms(concern_tokens, resource, limit=4):
    """Words shared by the concern and the resource, for 'why this?'."""
    resource_words = re.findall(r"[a-z]+", build_resource_text(resource).lower())
    seen = []
    for word in resource_words:
        if _stem(word) in concern_tokens and word not in seen and word not in STOPWORDS:
            seen.append(word)
        if len(seen) >= limit:
            break
    return seen


def keyword_rank(concern, resources, limit):
    """
    Fallback ranker used only when the embedding model is unavailable.
    Scores = weighted share of concern keywords found in the resource,
    with title/topic matches counting three times as much as body text.
    """
    query = tokenize(f"{concern.symptom} {concern.description}")
    if not query:
        return []

    ranked = []
    for resource in resources:
        head = tokenize(f"{resource.title} {resource.topic}")
        body = tokenize(f"{resource.description} {resource.content}")
        score = sum(3 if t in head else 1 if t in body else 0 for t in query)
        if score >= 2:
            ranked.append({
                "resource": resource,
                "score": round(score / (3 * len(query)), 3),
                "confidence": "keyword",
                "matched_terms": matched_terms(query, resource),
            })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def _dot(a, b):
    # Both vectors are L2-normalized, so the dot product is cosine similarity.
    return sum(x * y for x, y in zip(a, b))


def recommend_resources(concern, limit=5, min_score=BASELINE_MIN_SCORE):
    """
    BASELINE ranking (original implementation, unchanged behaviour).
    Returns a ranked list of {"resource", "score"} dicts.
    """
    if not concern or not concern.description.strip():
        return []

    concern_text = build_concern_text(concern)

    if not concern_text.strip():
        return []

    query_embedding = create_embedding(concern_text)

    resources = EducationalResource.objects.exclude(
        content=""
    )

    recommendations = []

    for resource in resources:
        resource_embedding = get_resource_embedding(resource)

        if resource_embedding is None:
            continue

        similarity = _dot(query_embedding, resource_embedding)

        if similarity >= min_score:
            recommendations.append({
                "resource": resource,
                "score": round(similarity, 3),
            })

    recommendations.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return recommendations[:limit]


def hybrid_rank(query_vector, resource_vectors, limit=5):
    """
    Confidence-aware selection over cosine similarities.

    * every resource scoring >= STRONG_MATCH is returned as "strong";
    * if none is strong, resources scoring >= POSSIBLE_MATCH are returned
      as "possible" (added after evaluation iteration 1, see AI_REPORT.md);
    * if there are still none, the single best resource is returned as
      "possible" when it scores >= POSSIBLE_MATCH_FLOOR *and* beats the
      runner-up by DISTINCT_MARGIN (a clearly separated match is more
      trustworthy than a high but ambiguous one);
    * otherwise nothing is returned, which the UI reports honestly.
    """
    scored = sorted(
        ((resource, _dot(query_vector, vector)) for resource, vector in resource_vectors),
        key=lambda pair: pair[1],
        reverse=True,
    )

    if not scored:
        return []

    strong = [
        {"resource": r, "score": round(s, 3), "confidence": "strong"}
        for r, s in scored if s >= STRONG_MATCH
    ]
    if strong:
        return strong[:limit]

    possible = [
        {"resource": r, "score": round(s, 3), "confidence": "possible"}
        for r, s in scored if s >= POSSIBLE_MATCH
    ]
    if possible:
        return possible[:limit]

    best_resource, best = scored[0]
    runner_up = scored[1][1] if len(scored) > 1 else 0.0

    if best >= POSSIBLE_MATCH_FLOOR and best - runner_up >= DISTINCT_MARGIN:
        return [{"resource": best_resource, "score": round(best, 3), "confidence": "possible"}]

    return []


def _has_meaningful_input(concern):
    text = f"{_clean(concern.symptom)} {_clean(concern.description)}"
    return len(re.sub(r"[^a-zA-Z]", "", text)) >= MIN_MEANINGFUL_CHARS


def get_recommendations(concern, strategy="hybrid", limit=5):
    """
    Main entry point used by the Django views.

    Never raises: every failure mode is reported through
    ``RecommendationResult.status`` and a user-facing ``message``.
    The safety screen runs first and is returned even if the model fails.
    """
    start = time.perf_counter()
    result = RecommendationResult(strategy=strategy)

    try:
        if concern is None:
            result.status = INSUFFICIENT_INPUT
            result.message = "No health concern was provided."
            return result

        if strategy == "hybrid":
            result.safety_alert = screen_concern(concern)

        if not _has_meaningful_input(concern):
            result.status = INSUFFICIENT_INPUT
            result.message = (
                "Add a few words describing your symptom so we can "
                "find relevant resources."
            )
            return result

        if strategy == "baseline":
            result.recommendations = recommend_resources(concern, limit=limit)
        else:
            _run_hybrid(concern, result, limit)

        if result.status == OK and not result.recommendations:
            result.status = NO_MATCH
            result.message = (
                "We don't have a resource that closely matches this "
                "concern yet. Your provider is the best source of "
                "information about it."
            )

    except Exception:  # noqa: BLE001 - views must always get a result
        logger.exception("Recommendation pipeline failed (strategy=%s).", strategy)
        result.recommendations = []
        result.status = ERROR
        result.message = (
            "We couldn't load educational resources right now. "
            "Please try again later."
        )

    finally:
        result.latency_ms = round((time.perf_counter() - start) * 1000, 1)

    return result


def _run_hybrid(concern, result, limit):
    query_text = build_query_text(concern)
    query_tokens = tokenize(query_text)

    try:
        query_vector = encode_texts([query_text])[0]
        resource_vectors = load_resource_embeddings()
    except EmbeddingError:
        # Log without patient text: only the fact that the model failed.
        logger.warning("Embedding model unavailable; using keyword fallback.")
        resources = list(EducationalResource.objects.exclude(content=""))
        result.recommendations = keyword_rank(concern, resources, limit)
        result.status = FALLBACK
        result.message = (
            "Our smart matching is temporarily unavailable, so these "
            "results are based on keyword matching and may be less precise."
        )
        return

    recommendations = hybrid_rank(query_vector, resource_vectors, limit)

    for item in recommendations:
        item["matched_terms"] = matched_terms(query_tokens, item["resource"])

    result.recommendations = recommendations
