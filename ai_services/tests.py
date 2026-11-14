
from django.test import TestCase
from unittest.mock import patch

from appointments.models import EducationalResource, HealthConcern
from ai_services.resource_recommender import (
    build_concern_text,
    build_resource_text,
    recommend_resources,
)


class ResourceRecommenderTests(TestCase):


    @patch("ai_services.resource_recommender.create_embedding")
    def test_resources_are_ranked_by_similarity(self, mock_embedding):
        mock_embedding.side_effect = [
            [1.0] + [0.0] * 383,  # Concern
            [0.5, 0.8660254] + [0.0] * 382,  # First resource
            [1.0] + [0.0] * 383,  # Second resource
        ]

        first_resource = EducationalResource.objects.create(
            title="Understanding Sleep",
            description="Information about sleep.",
            topic="Sleep",
            content="Sleep affects overall health.",
            source="Test Source",
            url="https://example.com/sleep",
        )

        second_resource = EducationalResource.objects.create(
            title="Understanding Headaches",
            description="Information about headaches.",
            topic="Headaches",
            content="Headaches can have different causes.",
            source="Test Source",
            url="https://example.com/headaches",
        )

        concern = HealthConcern(
            symptom="Headaches",
            description="Frequent headaches",
            frequency="Daily",
            duration="Two weeks",
            severity=5,
        )

        results = recommend_resources(concern)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["resource"], second_resource)
        self.assertEqual(results[1]["resource"], first_resource)
        self.assertGreater(
            results[0]["score"],
            results[1]["score"]
        )


    def test_build_resource_text(self):
        resource = EducationalResource(
            title="Understanding Headaches",
            description="Information about headaches.",
            topic="Headaches",
            content="Headaches can have different causes."
        )

        result = build_resource_text(resource)

        self.assertIn("Understanding Headaches", result)
        self.assertIn("Headaches", result)

    def test_build_concern_text(self):
        concern = HealthConcern(
            symptom="Headaches",
            description="Frequent headaches",
            frequency="Daily",
            duration="Two weeks",
            severity=5
        )

        result = build_concern_text(concern)

        self.assertIn("Headaches", result)
        self.assertIn("Frequent headaches", result)

    def test_empty_concern_returns_no_recommendations(self):
        concern = HealthConcern(
            symptom="",
            description=""
        )

        self.assertEqual(recommend_resources(concern), [])


    @patch("ai_services.resource_recommender.create_embedding")
    def test_relevant_resource_is_recommended(self, mock_embedding):
        mock_embedding.side_effect = [
            [1.0] + [0.0] * 383,  # Concern embedding
            [1.0] + [0.0] * 383,  # Resource embedding
        ]

        resource = EducationalResource.objects.create(
            title="Understanding Headaches",
            description="Information about headaches.",
            topic="Headaches",
            content="Headaches can have different causes.",
            source="Test Source",
            url="https://example.com/headaches",
        )

        concern = HealthConcern(
            symptom="Headaches",
            description="Frequent headaches",
            frequency="Daily",
            duration="Two weeks",
            severity=5,
        )

        results = recommend_resources(concern)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource"], resource)
        self.assertEqual(results[0]["score"], 1.0)

    @patch("ai_services.resource_recommender.create_embedding")
    def test_low_similarity_resource_is_filtered(self, mock_embedding):
        mock_embedding.side_effect = [
            [1.0] + [0.0] * 383,
            [0.0, 1.0] + [0.0] * 382,
        ]

        EducationalResource.objects.create(
            title="Understanding Headaches",
            description="Information about headaches.",
            topic="Headaches",
            content="Headaches can have different causes.",
            source="Test Source",
            url="https://example.com/headaches",
        )

        concern = HealthConcern(
            symptom="Headaches",
            description="Frequent headaches",
            frequency="Daily",
            duration="Two weeks",
            severity=5,
        )

        results = recommend_resources(concern)

        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# Hybrid recommender, reliability and safety tests
# ---------------------------------------------------------------------------

from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from ai_services import resource_recommender as rr
from ai_services.safety import CRISIS, EMERGENCY, screen_text


def unit(*weights):
    """Build a normalized 384-dim vector from leading weights."""
    vector = list(weights) + [0.0] * (rr.EMBEDDING_DIM - len(weights))
    norm = sum(v * v for v in vector) ** 0.5
    return [v / norm for v in vector]


def make_resource(title, topic, **extra):
    return EducationalResource.objects.create(
        title=title,
        description=f"Information about {topic.lower()}.",
        topic=topic,
        content=f"{topic} can have many causes and treatments.",
        source="Test Source",
        url=f"https://example.com/{topic.lower().replace(' ', '-')}",
        **extra,
    )


class HybridRankTests(TestCase):

    def setUp(self):
        self.a = make_resource("A", "Alpha")
        self.b = make_resource("B", "Beta")
        self.c = make_resource("C", "Gamma")

    def test_strong_matches_returned_in_order(self):
        query = unit(1.0)
        vectors = [
            (self.a, unit(0.5, 0.866)),   # 0.50
            (self.b, unit(1.0)),          # 1.00
            (self.c, unit(0.0, 1.0)),     # 0.00
        ]
        results = rr.hybrid_rank(query, vectors)
        self.assertEqual([r["resource"] for r in results], [self.b, self.a])
        self.assertTrue(all(r["confidence"] == "strong" for r in results))

    def test_possible_band_is_labelled(self):
        query = unit(1.0)
        vectors = [(self.a, unit(0.42, (1 - 0.42 ** 2) ** 0.5))]
        results = rr.hybrid_rank(query, vectors)
        self.assertEqual(results[0]["confidence"], "possible")

    def test_distinctive_low_score_top_match_is_kept(self):
        query = unit(1.0)
        vectors = [
            (self.a, unit(0.35, (1 - 0.35 ** 2) ** 0.5)),  # 0.35
            (self.b, unit(0.20, (1 - 0.20 ** 2) ** 0.5)),  # 0.20
        ]
        results = rr.hybrid_rank(query, vectors)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource"], self.a)

    def test_ambiguous_low_scores_return_nothing(self):
        query = unit(1.0)
        vectors = [
            (self.a, unit(0.33, (1 - 0.33 ** 2) ** 0.5)),
            (self.b, unit(0.31, (1 - 0.31 ** 2) ** 0.5)),
        ]
        self.assertEqual(rr.hybrid_rank(query, vectors), [])


class QueryTextTests(TestCase):

    def test_empty_fields_are_not_included(self):
        concern = HealthConcern(symptom="Cough", description="Dry cough", severity=3)
        text = rr.build_query_text(concern)
        self.assertEqual(text, "Cough. Dry cough")
        self.assertNotIn("Possible triggers", text)

    def test_frequency_uses_human_label(self):
        concern = HealthConcern(
            symptom="Cough", description="Dry cough", frequency="daily", severity=3
        )
        self.assertIn("Happens: Daily", rr.build_query_text(concern))


class GetRecommendationsReliabilityTests(TestCase):

    def setUp(self):
        self.headache = make_resource("Understanding Headaches", "Headache")
        self.sleep = make_resource("Better Sleep", "Insomnia")
        self.concern = HealthConcern(
            symptom="Headache", description="Throbbing headache every day", severity=5
        )

    @patch("ai_services.resource_recommender.encode_texts")
    def test_happy_path_returns_ok_with_explanations(self, mock_encode):
        mock_encode.side_effect = [
            [unit(1.0)],                         # query
            [unit(1.0), unit(0.0, 1.0)],         # resources (headache, sleep)
        ]
        result = rr.get_recommendations(self.concern)
        self.assertEqual(result.status, rr.OK)
        self.assertEqual(result.recommendations[0]["resource"], self.headache)
        self.assertIn("headache", result.recommendations[0]["matched_terms"])
        # Embeddings were cached in the database.
        self.headache.refresh_from_db()
        self.assertEqual(len(self.headache.embedding), rr.EMBEDDING_DIM)

    @patch("ai_services.resource_recommender.get_embedding_model")
    def test_model_unavailable_falls_back_to_keywords(self, mock_model):
        mock_model.side_effect = OSError("model download failed")
        result = rr.get_recommendations(self.concern)
        self.assertEqual(result.status, rr.FALLBACK)
        self.assertIn("keyword", result.message)
        self.assertEqual(result.recommendations[0]["resource"], self.headache)
        self.assertEqual(result.recommendations[0]["confidence"], "keyword")

    @patch("ai_services.resource_recommender.get_embedding_model")
    def test_invalid_model_output_falls_back(self, mock_model):
        import numpy as np

        mock_model.return_value.encode.return_value = np.array([[float("nan")] * 10])
        result = rr.get_recommendations(self.concern)
        self.assertEqual(result.status, rr.FALLBACK)

    @patch("ai_services.resource_recommender.encode_texts")
    def test_corrupted_stored_embedding_is_recomputed(self, mock_encode):
        EducationalResource.objects.filter(pk=self.headache.pk).update(embedding=[1, 2, 3])
        EducationalResource.objects.filter(pk=self.sleep.pk).update(embedding=unit(0.0, 1.0))
        mock_encode.side_effect = [[unit(1.0)], [unit(1.0)]]

        result = rr.get_recommendations(self.concern)

        self.assertEqual(result.status, rr.OK)
        # Only the corrupted resource was re-embedded.
        self.assertEqual(len(mock_encode.call_args_list[1].args[0]), 1)

    @patch("ai_services.resource_recommender.load_resource_embeddings")
    @patch("ai_services.resource_recommender.encode_texts")
    def test_unexpected_error_is_reported_not_raised(self, mock_encode, mock_load):
        mock_encode.return_value = [unit(1.0)]
        mock_load.side_effect = ValueError("database exploded")
        result = rr.get_recommendations(self.concern)
        self.assertEqual(result.status, rr.ERROR)
        self.assertEqual(result.recommendations, [])
        self.assertTrue(result.message)

    def test_insufficient_input(self):
        concern = HealthConcern(symptom="??", description="!!", severity=1)
        result = rr.get_recommendations(concern)
        self.assertEqual(result.status, rr.INSUFFICIENT_INPUT)

    def test_none_concern(self):
        self.assertEqual(rr.get_recommendations(None).status, rr.INSUFFICIENT_INPUT)

    @patch("ai_services.resource_recommender.encode_texts")
    def test_no_match_status_when_nothing_relevant(self, mock_encode):
        mock_encode.side_effect = [
            [unit(1.0)],
            [unit(0.0, 1.0), unit(0.0, 0.0, 1.0)],
        ]
        result = rr.get_recommendations(self.concern)
        self.assertEqual(result.status, rr.NO_MATCH)

    @patch("ai_services.resource_recommender.get_embedding_model")
    def test_safety_alert_survives_model_failure(self, mock_model):
        mock_model.side_effect = OSError("offline")
        concern = HealthConcern(
            symptom="Chest pain",
            description="Crushing chest pressure spreading to my left arm",
            severity=9,
        )
        result = rr.get_recommendations(concern)
        self.assertIsNotNone(result.safety_alert)
        self.assertEqual(result.safety_alert.level, EMERGENCY)


class SafetyScreenTests(TestCase):

    def test_cardiac_emergency(self):
        alert = screen_text("Chest pain that spreads to my jaw and I'm sweating")
        self.assertEqual(alert.level, EMERGENCY)
        self.assertEqual(alert.category, "cardiac")

    def test_breathing_emergency(self):
        self.assertEqual(screen_text("I can't breathe").category, "breathing")

    def test_self_harm_is_crisis_with_988(self):
        alert = screen_text("I keep thinking about ending my life")
        self.assertEqual(alert.level, CRISIS)
        self.assertIn("988", alert.message)

    def test_ordinary_symptoms_are_not_flagged(self):
        for text in [
            "Mild headache after work",
            "Sore knee after running",
            "Chest feels congested from a cold",
            "",
        ]:
            self.assertIsNone(screen_text(text), text)


class RecommendationViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("pat", password="test-pass-123")
        self.other = User.objects.create_user("sam", password="test-pass-123")
        appointment = Appointment.objects.create(
            user=self.user,
            doctor_name="Dr. Lee",
            appointment_date=timezone.now() + timedelta(days=3),
            reason_for_visit="Check-up",
        )
        self.concern = HealthConcern.objects.create(
            appointment=appointment,
            symptom="Chest pain",
            description="Crushing pressure in my chest spreading to my left arm",
            severity=9,
        )
        self.client.login(username="pat", password="test-pass-123")

    @patch("ai_services.resource_recommender.get_embedding_model")
    def test_page_renders_when_model_fails(self, mock_model):
        mock_model.side_effect = OSError("offline")
        response = self.client.get(reverse("recommended_resources", args=[self.concern.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "keyword matching")
        self.assertContains(response, "911")

    def test_other_users_concern_is_not_accessible(self):
        self.client.logout()
        self.client.login(username="sam", password="test-pass-123")
        response = self.client.get(reverse("recommended_resources", args=[self.concern.pk]))
        self.assertEqual(response.status_code, 404)

    def test_appointment_detail_shows_safety_banner(self):
        response = self.client.get(
            reverse("appointment_detail", args=[self.concern.appointment.pk])
        )
        self.assertContains(response, "This may need urgent care")

    def test_pre_visit_summary_flags_concern(self):
        response = self.client.get(
            reverse("pre_visit_summary", args=[self.concern.appointment.pk])
        )
        self.assertContains(response, "possible warning sign")
