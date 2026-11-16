import json
from pathlib import Path

from django.core.management.base import BaseCommand

from appointments.models import EducationalResource


DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "resources.json"


class Command(BaseCommand):
    help = (
        "Load the curated educational-resource library used by the "
        "AI recommender. Existing resources are matched by URL and "
        "updated in place, so the command is safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--embed",
            action="store_true",
            help="Pre-compute embeddings now instead of on first request.",
        )

    def handle(self, *args, **options):
        records = json.loads(DATA_FILE.read_text(encoding="utf-8"))

        created = updated = 0

        for record in records:
            resource = EducationalResource.objects.filter(
                url=record["url"]
            ).first()

            if resource is None:
                EducationalResource.objects.create(**record)
                created += 1
                continue

            for field, value in record.items():
                setattr(resource, field, value)

            # The model's save() clears stale embeddings when text changes.
            resource.save()
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Resources created: {created}, updated: {updated}."
        ))

        if options["embed"]:
            from ai_services.resource_recommender import get_resource_embedding

            count = sum(
                get_resource_embedding(resource) is not None
                for resource in EducationalResource.objects.all()
            )
            self.stdout.write(self.style.SUCCESS(
                f"Embeddings computed for {count} resources."
            ))
