
from django import forms
from .models import Appointment
from .models import HealthConcern
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Appointment, HealthConcern, VisitInstruction

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = [
            "doctor_name",
            "appointment_date",
            "reason_for_visit",
        ]

        widgets = {
            "appointment_date": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M"
            ),
        }

    appointment_date = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M"
        )
    )

    def clean_doctor_name(self):
        doctor_name = self.cleaned_data["doctor_name"].strip()

        if len(doctor_name) < 2:
            raise forms.ValidationError(
                "Please enter a valid doctor's name."
            )

        return doctor_name

class HealthConcernForm(forms.ModelForm):
    class Meta:
        model = HealthConcern

        fields = [
            "symptom",
            "description",
            "severity",
            "question_for_doctor",
        ]

        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Describe what you've been experiencing..."
                }
            ),

            "severity": forms.NumberInput(
                attrs={
                    "min": 1,
                    "max": 10
                }
            ),

            "question_for_doctor": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "What would you like to ask your doctor?"
                }
            ),
        }

    def clean_symptom(self):
        symptom = self.cleaned_data["symptom"].strip()

        if len(symptom) < 3:
            raise forms.ValidationError(
                "Please describe your symptom in at least 3 characters."
            )

        return symptom

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User

        fields = [
            "username",
            "email",
            "password1",
            "password2",
        ]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )

        return email

class VisitInstructionForm(forms.ModelForm):
    class Meta:
        model = VisitInstruction

        fields = [
            "instruction",
            "completed",
        ]

        widgets = {
            "instruction": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Enter your doctor's recommendations or follow-up instructions..."
                }
            ),
        }

    def clean_instruction(self):
        instruction = self.cleaned_data["instruction"].strip()

        if len(instruction) < 5:
            raise forms.ValidationError(
                "Please enter a more detailed instruction."
            )

        return instruction
