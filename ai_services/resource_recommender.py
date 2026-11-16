
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from appointments.models import EducationalResource


# Lightweight semantic-search model
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Part 4.4 improvement: confidence tiers replace the single 0.45 cutoff.
# Chosen from the evaluation documented in AI_REPORT.md.
BASELINE_MIN_SCORE = 0.45
STRONG_MATCH = 0.45          # every resource at/above this is shown
POSSIBLE_MATCH = 0.40        # if none is strong, show the 0.40-0.45 band
DISTINCT_FLOOR = 0.30        # else show the single best resource if it is
DISTINCT_MARGIN = 0.10       # >= 0.30 and beats the runner-up by >= 0.10


@lru_cache(maxsize=1)
def get_embedding_model():
    """
    Load the embedding model once and reuse it.
    CPU is used to support computers without a compatible GPU.
    """
    return SentenceTransformer(MODEL_NAME, device="cpu")



def build_concern_text(concern):
    """
    Give the primary symptom more importance while
    retaining the patient's additional context.
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
    )[:3000]



def build_query_text(concern):
    """
    IMPROVED query text (Part 4.4): include only the fields the patient
    actually filled in. The original build_concern_text() always emitted
    every label ("Possible triggers: ." ...) and repeated the symptom,
    which made all queries look alike and compressed similarity scores.
    """
    frequency = (
        concern.get_frequency_display() if concern.frequency else ""
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
        value = " ".join(str(value or "").split())
        if value:
            parts.append(f"{label}: {value}" if label else value)

    return ". ".join(parts)[:3000]


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
    )[:3000]


def create_embedding(text):
    """
    Convert text into a normalized numerical embedding.
    """
    model = get_embedding_model()

    embedding = model.encode(
        text,
        normalize_embeddings=True
    )

    return embedding.tolist()


def get_resource_embedding(resource):
    """
    Reuse an existing resource embedding when available.
    Otherwise, generate one and save it to the database.
    """
    embedding = resource.embedding

    if isinstance(embedding, list) and len(embedding) == 384:
        return embedding

    resource_text = build_resource_text(resource)

    if not resource_text.strip():
        return None

    embedding = create_embedding(resource_text)

    resource.embedding = embedding
    resource.save(update_fields=["embedding"])

    return embedding


def select_recommendations(scored, limit):
    """
    IMPROVED selection (Part 4.4). ``scored`` is a list of
    (resource, similarity) sorted best-first.
    """
    if not scored:
        return []

    strong = [(r, s) for r, s in scored if s >= STRONG_MATCH]
    if strong:
        return strong[:limit]

    possible = [(r, s) for r, s in scored if s >= POSSIBLE_MATCH]
    if possible:
        return possible[:limit]

    best_resource, best = scored[0]
    runner_up = scored[1][1] if len(scored) > 1 else 0.0

    if best >= DISTINCT_FLOOR and best - runner_up >= DISTINCT_MARGIN:
        return [(best_resource, best)]

    return []


def recommend_resources(concern, limit=5, min_score=None, strategy="improved"):
    """
    Find educational resources that are semantically
    similar to a patient's health concern.

    strategy="baseline" reproduces the original implementation
    (templated query + single fixed threshold) for evaluation.
    strategy="improved" is the default used by the app.

    Returns a ranked list of resources and similarity scores.
    """
    if not concern or not concern.description.strip():
        return []

    if strategy == "baseline":
        concern_text = build_concern_text(concern)
    else:
        concern_text = build_query_text(concern)

    if not concern_text.strip():
        return []

    query_embedding = create_embedding(concern_text)

    resources = EducationalResource.objects.exclude(
        content=""
    )

    scored = []

    for resource in resources:
        resource_embedding = get_resource_embedding(resource)

        if resource_embedding is None:
            continue

        # Both embeddings are normalized, so their dot product
        # represents cosine similarity.
        similarity = sum(
            query_value * resource_value
            for query_value, resource_value in zip(
                query_embedding,
                resource_embedding
            )
        )

        scored.append((resource, similarity))

    scored.sort(key=lambda pair: pair[1], reverse=True)

    if strategy == "baseline" or min_score is not None:
        threshold = BASELINE_MIN_SCORE if min_score is None else min_score
        selected = [(r, s) for r, s in scored if s >= threshold][:limit]
    else:
        selected = select_recommendations(scored, limit)

    return [
        {"resource": resource, "score": round(score, 3)}
        for resource, score in selected
    ]
