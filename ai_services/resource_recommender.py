
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from appointments.models import EducationalResource


# Lightweight semantic-search model
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


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


def recommend_resources(concern, limit=5, min_score=0.45):
    """
    Find educational resources that are semantically
    similar to a patient's health concern.

    Returns a ranked list of resources and similarity scores.
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

        # Both embeddings are normalized, so their dot product
        # represents cosine similarity.
        similarity = sum(
            query_value * resource_value
            for query_value, resource_value in zip(
                query_embedding,
                resource_embedding
            )
        )

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
