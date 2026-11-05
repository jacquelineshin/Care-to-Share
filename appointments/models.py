
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
    question_for_doctor = models.TextField(blank=True)

    def __str__(self):
        return self.symptom


class VisitInstruction(models.Model):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="instructions"
    )
    instruction = models.TextField()
    completed = models.BooleanField(default=False)

    def __str__(self):
        return self.instruction[:50]
