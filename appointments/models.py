
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Appointment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    doctor_name = models.CharField(max_length=100)
    appointment_date = models.DateTimeField()
    reason_for_visit = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.doctor_name} - {self.appointment_date.date()}"



class HealthConcern(models.Model):

    FREQUENCY_CHOICES = [
        ("daily", "Daily"),
        ("several_weekly", "Several times per week"),
        ("weekly", "Once per week"),
        ("monthly", "Several times per month"),
        ("occasionally", "Occasionally"),
        ("other", "Other"),
    ]

    PRIORITY_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="concerns"
    )

    symptom = models.CharField(max_length=200)

    description = models.TextField()

    severity = models.IntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(10)
        ]
    )

    onset_date = models.DateField(
        null=True,
        blank=True
    )

    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        blank=True
    )

    duration = models.CharField(
        max_length=100,
        blank=True
    )

    triggers = models.TextField(
        blank=True
    )

    relieving_factors = models.TextField(
        blank=True
    )

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="medium"
    )

    question_for_doctor = models.TextField(
        blank=True
    )

    def __str__(self):
        return self.symptom



class VisitInstruction(models.Model):

    CATEGORY_CHOICES = [
        ("medication", "Medications"),
        ("follow_up", "Follow-Up Appointments"),
        ("lifestyle", "Lifestyle Recommendations"),
        ("tests", "Tests and Procedures"),
        ("other", "Other Instructions"),
    ]

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="instructions"
    )

    instruction = models.TextField()

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="other"
    )

    due_date = models.DateField(
        null=True,
        blank=True
    )

    completed = models.BooleanField(
        default=False
    )

    def __str__(self):
        return self.instruction[:50]


class EducationalResource(models.Model):

    title = models.CharField(max_length=200)
    description = models.TextField()
    content = models.TextField()
    topic = models.CharField(max_length=100)
    source = models.CharField(max_length=200)
    url = models.URLField()

    embedding = models.JSONField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Check whether searchable article information changed.
        if self.pk:
            old_resource = EducationalResource.objects.filter(
                pk=self.pk
            ).first()

            if old_resource:
                changed_fields = [
                    "title",
                    "description",
                    "content",
                    "topic",
                ]

                if any(
                    getattr(old_resource, field) != getattr(self, field)
                    for field in changed_fields
                ):
                    self.embedding = None

                    if kwargs.get("update_fields") is not None:
                        kwargs["update_fields"] = (
                            set(kwargs["update_fields"]) | {"embedding"}
                        )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
