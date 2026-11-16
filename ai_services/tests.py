
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
