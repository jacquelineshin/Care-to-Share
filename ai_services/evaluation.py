"""
Offline evaluation harness for the educational-resource recommender
(Part 4: consistent evaluation procedure).

Every test case is a realistic HealthConcern plus the set of resource
topics the team judged relevant. The same cases, metrics and scoring
rubric are applied to every strategy so results are directly comparable.
"""

import json
import statistics
import time
from pathlib import Path

from appointments.models import HealthConcern


DATA_DIR = Path(__file__).resolve().parent / "data"
CASES_FILE = DATA_DIR / "eval_cases.json"

CONCERN_FIELDS = [
    "symptom",
    "description",
    "frequency",
    "duration",
    "triggers",
    "relieving_factors",
    "question_for_doctor",
]


def load_cases(path=CASES_FILE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_concern(case):
    values = {field: case.get(field, "") for field in CONCERN_FIELDS}
    values["severity"] = case.get("severity", 5)
    return HealthConcern(**values)


def quality_score(case, topics, errored=False):
    """
    Deterministic 1-10 quality rubric.

    In-scope cases:   4 pts if the top result is relevant,
                      2 pts if any of the top 3 is relevant,
                      4 pts x precision of everything shown.
                      No results at all scores 1.
    No-match cases    10 if nothing is shown, minus 2 per
    (out of scope /   irrelevant result (an honest "no match"
    not covered):     is the correct behaviour).
    Pipeline error:   1.
    """
    if errored:
        return 1

    relevant = set(case["relevant"])

    if not relevant:
        score = 10 - 2 * len(topics)
    elif not topics:
        score = 1
    else:
        hit1 = topics[0] in relevant
        hit3 = any(topic in relevant for topic in topics[:3])
        precision = sum(topic in relevant for topic in topics) / len(topics)
        score = 4 * hit1 + 2 * hit3 + 4 * precision

    return max(1, min(10, round(score)))


def run_case(case, strategy):
    from ai_services.resource_recommender import recommend_resources

    concern = build_concern(case)
    errored = False

    start = time.perf_counter()
    try:
        recommendations = recommend_resources(concern, strategy=strategy)
    except Exception:  # noqa: BLE001 - errors are a measured outcome
        recommendations = []
        errored = True
    latency_ms = (time.perf_counter() - start) * 1000

    topics = [item["resource"].topic for item in recommendations]
    relevant = set(case["relevant"])

    row = {
        "id": case["id"],
        "category": case["category"],
        "symptom": case["symptom"],
        "description": case["description"],
        "relevant": case["relevant"],
        "returned": [
            {"topic": item["resource"].topic, "score": item["score"]}
            for item in recommendations
        ],
        "error": errored,
        "latency_ms": round(latency_ms, 1),
    }

    if relevant:
        rank = next(
            (i + 1 for i, topic in enumerate(topics) if topic in relevant),
            None,
        )
        row["hit_at_1"] = bool(topics) and topics[0] in relevant
        row["hit_at_3"] = rank is not None and rank <= 3
        row["reciprocal_rank"] = 1 / rank if rank else 0.0
        row["precision"] = (
            sum(topic in relevant for topic in topics) / len(topics)
            if topics else 0.0
        )
        row["empty"] = not topics
    else:
        row["false_positive"] = bool(topics)

    row["quality"] = quality_score(case, topics, errored)
    return row


def summarize(rows):
    in_scope = [r for r in rows if r["relevant"]]
    no_match = [r for r in rows if not r["relevant"]]
    latencies = sorted(r["latency_ms"] for r in rows)

    def mean(values):
        return round(statistics.mean(values), 3) if values else 0.0

    return {
        "cases": len(rows),
        "hit_at_1": mean([r["hit_at_1"] for r in in_scope]),
        "hit_at_3": mean([r["hit_at_3"] for r in in_scope]),
        "mrr": mean([r["reciprocal_rank"] for r in in_scope]),
        "precision": mean([r["precision"] for r in in_scope]),
        "empty_rate_in_scope": mean([r["empty"] for r in in_scope]),
        "false_positive_rate": mean([r["false_positive"] for r in no_match]),
        "error_rate": mean([r["error"] for r in rows]),
        "mean_quality": mean([r["quality"] for r in rows]),
        "latency_p50_ms": round(statistics.median(latencies), 1),
        "latency_p95_ms": round(
            latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))], 1
        ),
    }


def run_evaluation(strategy, cases_file=CASES_FILE):
    from ai_services.resource_recommender import get_embedding_model

    start = time.perf_counter()
    get_embedding_model()
    model_load_ms = (time.perf_counter() - start) * 1000

    rows = [run_case(case, strategy) for case in load_cases(cases_file)]
    summary = summarize(rows)
    summary["strategy"] = strategy
    summary["model_load_ms"] = round(model_load_ms, 1)

    return {"summary": summary, "rows": rows}
