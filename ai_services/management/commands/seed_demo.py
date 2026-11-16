from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import Appointment, HealthConcern


DEMO_USERNAME = "demo"
DEMO_PASSWORD = "care-demo-2026"  # local demo account only


CONCERNS = [
    dict(symptom="Pounding headaches", severity=7, priority="high", frequency="several_weekly",
         description="Throbbing on one side of my head with flashing lights before it starts. Light makes it worse.",
         triggers="bright screens, skipping lunch", question_for_doctor="Could these be migraines?"),
    dict(symptom="Always tired", severity=5, priority="medium", frequency="daily",
         description="No energy even after sleeping 9 hours. Hard to get through the work day.",
         duration="about a month"),
    dict(symptom="Chest pain", severity=9, priority="high",
         description="Crushing pressure in my chest that spreads to my left arm, with sweating."),
    dict(symptom="Toothache", severity=6, priority="low",
         description="Sharp pain in a back molar when I drink something cold."),
]


class Command(BaseCommand):
    help = "Create a local demo user with an appointment and sample concerns."

    def handle(self, *args, **options):
        call_command("seed_resources", embed=True)

        user, created = User.objects.get_or_create(username=DEMO_USERNAME)
        user.set_password(DEMO_PASSWORD)
        user.save()

        appointment, _ = Appointment.objects.get_or_create(
            user=user,
            doctor_name="Dr. Rivera",
            defaults={
                "appointment_date": timezone.now() + timedelta(days=5),
                "reason_for_visit": "Recurring headaches and low energy",
            },
        )

        for data in CONCERNS:
            HealthConcern.objects.update_or_create(
                appointment=appointment, symptom=data["symptom"], defaults=data
            )

        self.stdout.write(self.style.SUCCESS(
            f"Demo user '{DEMO_USERNAME}' ready (password in seed_demo.py)."
        ))
