
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
# Part 4.4 improvement tests
# ---------------------------------------------------------------------------

from ai_services.resource_recommender import (
    build_query_text,
    select_recommendations,
)


class ImprovedQueryTextTests(TestCase):

    def test_empty_fields_are_left_out(self):
        concern = HealthConcern(symptom="Cough", description="Dry cough", severity=3)
        text = build_query_text(concern)
        self.assertEqual(text, "Cough. Dry cough")
        self.assertNotIn("Possible triggers", text)
        self.assertNotIn("severity", text.lower())

    def test_frequency_uses_human_label(self):
        concern = HealthConcern(
            symptom="Cough", description="Dry cough", frequency="daily", severity=3
        )
        self.assertIn("Happens: Daily", build_query_text(concern))


class ConfidenceTierTests(TestCase):

    def test_strong_matches_all_returned(self):
        scored = [("a", 0.7), ("b", 0.5), ("c", 0.2)]
        self.assertEqual(select_recommendations(scored, 5), [("a", 0.7), ("b", 0.5)])

    def test_possible_band_used_when_nothing_strong(self):
        scored = [("a", 0.43), ("b", 0.41), ("c", 0.2)]
        self.assertEqual(select_recommendations(scored, 5), [("a", 0.43), ("b", 0.41)])

    def test_distinctive_low_top_match_kept(self):
        scored = [("a", 0.35), ("b", 0.20)]
        self.assertEqual(select_recommendations(scored, 5), [("a", 0.35)])

    def test_ambiguous_low_scores_rejected(self):
        scored = [("a", 0.33), ("b", 0.31)]
        self.assertEqual(select_recommendations(scored, 5), [])

    def test_empty_input(self):
        self.assertEqual(select_recommendations([], 5), [])


class StrategyTests(TestCase):

    @patch("ai_services.resource_recommender.create_embedding")
    def test_improved_keeps_distinctive_match_baseline_drops_it(self, mock_embedding):
        # Resource A: similarity 0.35, resource B: 0.0
        a_vec = [0.35, (1 - 0.35 ** 2) ** 0.5] + [0.0] * 382
        b_vec = [0.0, 0.0, 1.0] + [0.0] * 381
        EducationalResource.objects.create(
            title="A", description="a", topic="A", content="a",
            source="s", url="https://example.com/a", embedding=a_vec,
        )
        EducationalResource.objects.create(
            title="B", description="b", topic="B", content="b",
            source="s", url="https://example.com/b", embedding=b_vec,
        )
        mock_embedding.return_value = [1.0] + [0.0] * 383
        concern = HealthConcern(symptom="Thirsty", description="Always thirsty", severity=4)

        baseline = recommend_resources(concern, strategy="baseline")
        improved = recommend_resources(concern)

        self.assertEqual(baseline, [])
        self.assertEqual([r["resource"].topic for r in improved], ["A"])


# ---------------------------------------------------------------------------
# Part 5 production-readiness tests
# ---------------------------------------------------------------------------

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment


class ProductionReadinessTests(TestCase):

    def setUp(self):
        cache.clear()
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
            symptom="Headache",
            description="Pressure headache every afternoon",
            severity=4,
        )
        self.url = reverse("recommended_resources", args=[self.concern.pk])

    def test_healthz(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], True)

    def test_recommendations_require_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_other_users_concern_is_404(self):
        self.client.login(username="sam", password="test-pass-123")
        self.assertEqual(self.client.get(self.url).status_code, 404)

    @override_settings(AI_RATE_LIMIT_PER_MINUTE=2)
    @patch("ai_services.resource_recommender.recommend_resources", return_value=[])
    def test_rate_limit_returns_429(self, _mock):
        self.client.login(username="pat", password="test-pass-123")
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")

    @patch(
        "ai_services.resource_recommender.recommend_resources",
        side_effect=RuntimeError("model crashed"),
    )
    def test_model_failure_fails_gracefully(self, _mock):
        self.client.login(username="pat", password="test-pass-123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "couldn&#x27;t load educational resources")


@override_settings(LOGIN_MAX_FAILURES=3, LOGIN_LOCKOUT_SECONDS=300)
class LoginThrottleTests(TestCase):

    def setUp(self):
        cache.clear()
        User.objects.create_user("pat", password="right-pass-123")
        self.url = reverse("login")

    def attempt(self, password, username="pat", ip="10.0.0.1"):
        return self.client.post(
            self.url,
            {"username": username, "password": password},
            REMOTE_ADDR=ip,
        )

    def test_correct_password_logs_in(self):
        response = self.attempt("right-pass-123")
        self.assertEqual(response.status_code, 302)

    def test_lockout_after_max_failures(self):
        for _ in range(3):
            self.assertEqual(self.attempt("wrong").status_code, 200)

        response = self.attempt("wrong")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "300")
        self.assertContains(response, "Too many failed login attempts", status_code=429)

    def test_locked_account_rejects_even_correct_password(self):
        for _ in range(3):
            self.attempt("wrong")
        response = self.attempt("right-pass-123")
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_username_lock_applies_from_other_ips(self):
        for i in range(3):
            self.attempt("wrong", ip=f"10.0.0.{i}")
        self.assertEqual(self.attempt("wrong", ip="10.9.9.9").status_code, 429)

    def test_ip_lock_applies_across_usernames(self):
        for i in range(3):
            self.attempt("wrong", username=f"guess{i}")
        self.assertEqual(self.attempt("wrong", username="someone").status_code, 429)

    def test_lock_is_case_insensitive(self):
        for _ in range(3):
            self.attempt("wrong", username="PAT", ip="10.1.1.1")
        self.assertEqual(self.attempt("wrong", username="pat", ip="10.2.2.2").status_code, 429)

    def test_success_resets_username_counter(self):
        self.attempt("wrong")
        self.attempt("wrong")
        self.assertEqual(self.attempt("right-pass-123").status_code, 302)
        self.client.logout()
        # Counter was cleared, so two more failures are allowed again.
        self.assertEqual(self.attempt("wrong", ip="10.3.3.3").status_code, 200)
        self.assertEqual(self.attempt("wrong", ip="10.3.3.3").status_code, 200)

    def test_lockout_expires(self):
        for _ in range(3):
            self.attempt("wrong")
        cache.clear()  # simulate the 5-minute window passing
        self.assertEqual(self.attempt("right-pass-123").status_code, 302)
