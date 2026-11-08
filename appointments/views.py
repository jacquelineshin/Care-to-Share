
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import login
from django.db.models import Q
from django.http import JsonResponse
from .forms import (
    AppointmentForm,
    HealthConcernForm,
    RegisterForm,
    VisitInstructionForm,
    HealthConcern,
)
from django.db.models import Case, When, Value, IntegerField
from .models import Appointment, HealthConcern, VisitInstruction
def home(request):
    return render(request, "appointments/home.html")



@login_required
def dashboard(request):
    query = request.GET.get("q", "").strip()

    appointments = Appointment.objects.filter(
        user=request.user
    )

    if query:
        appointments = appointments.filter(
            Q(doctor_name__icontains=query) |
            Q(reason_for_visit__icontains=query)
        )

    appointments = appointments.order_by(
        "appointment_date"
    )

    return render(
        request,
        "appointments/dashboard.html",
        {
            "appointments": appointments,
            "query": query
        }
    )



@login_required

@login_required
def appointment_detail(request, pk):

    appointment = get_object_or_404(
        Appointment,
        pk=pk,
        user=request.user
    )

    concerns = appointment.concerns.annotate(
        priority_order=Case(
            When(priority="high", then=Value(1)),
            When(priority="medium", then=Value(2)),
            When(priority="low", then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
    ).order_by("priority_order", "-severity")

    return render(
        request,
        "appointments/appointment_detail.html",
        {
            "appointment": appointment,
            "concerns": concerns
        }
    )

@login_required
def pre_visit_summary(request, pk):

    appointment = get_object_or_404(
        Appointment,
        pk=pk,
        user=request.user
    )

    concerns = appointment.concerns.annotate(
        priority_order=Case(
            When(priority="high", then=Value(1)),
            When(priority="medium", then=Value(2)),
            When(priority="low", then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
    ).order_by("priority_order", "-severity")

    return render(
        request,
        "appointments/pre_visit_summary.html",
        {
            "appointment": appointment,
            "concerns": concerns,
        }
    )


@login_required
def create_appointment(request):

    if request.method == "POST":
        form = AppointmentForm(request.POST)

        if form.is_valid():
            appointment = form.save(commit=False)

            appointment.user = request.user
            appointment.save()

            messages.success(
                request,
                "Your appointment was added successfully!"
            )

            return redirect("dashboard")

    else:
        form = AppointmentForm()

    return render(
        request,
        "appointments/appointment_form.html",
        {"form": form}
    )

@login_required
def edit_appointment(request, pk):
    appointment = get_object_or_404(
        Appointment,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":
        form = AppointmentForm(
            request.POST,
            instance=appointment
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Your appointment was updated successfully!"
            )

            return redirect(
                "appointment_detail",
                pk=appointment.pk
            )

    else:
        form = AppointmentForm(instance=appointment)

    return render(
        request,
        "appointments/appointment_form.html",
        {
            "form": form,
            "editing": True
        }
    )

@login_required
def delete_appointment(request, pk):
    appointment = get_object_or_404(
        Appointment,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":
        appointment.delete()

        messages.success(
            request,
            "Your appointment was deleted successfully."
        )

        return redirect("dashboard")

    return render(
        request,
        "appointments/appointment_confirm_delete.html",
        {"appointment": appointment}
    )

@login_required
def add_health_concern(request, pk):

    appointment = get_object_or_404(
        Appointment,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":
        form = HealthConcernForm(request.POST)

        if form.is_valid():
            concern = form.save(commit=False)

            concern.appointment = appointment
            concern.save()

            messages.success(
                request,
                "Your health concern was added successfully!"
            )

            return redirect(
                "appointment_detail",
                pk=appointment.pk
            )

    else:
        form = HealthConcernForm()

    return render(
        request,
        "appointments/health_concern_form.html",
        {
            "form": form,
            "appointment": appointment
        }
    )

def register(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save()

            login(request, user)

            messages.success(
                request,
                "Your account was created successfully!"
            )

            return redirect("dashboard")

    else:
        form = RegisterForm()

    return render(
        request,
        "appointments/register.html",
        {"form": form}
    )

@login_required
def delete_visit_instruction(request, pk):
    instruction = get_object_or_404(
        VisitInstruction,
        pk=pk,
        appointment__user=request.user
    )

    if request.method == "POST":
        appointment_pk = instruction.appointment.pk
        instruction.delete()

        messages.success(
            request,
            "Your visit instruction was deleted successfully."
        )

        return redirect(
            "appointment_detail",
            pk=appointment_pk
        )

    return render(
        request,
        "appointments/visit_instruction_confirm_delete.html",
        {"instruction": instruction}
    )

@login_required
def appointments_api(request):

    appointments = Appointment.objects.filter(
        user=request.user
    ).prefetch_related("concerns")

    data = []

    for appointment in appointments:

        concerns = []

        for concern in appointment.concerns.all():
            concerns.append({
                "symptom": concern.symptom,
                "description": concern.description,
                "severity": concern.severity,
                "question_for_doctor": concern.question_for_doctor,
            })

        data.append({
            "id": appointment.id,
            "doctor_name": appointment.doctor_name,
            "appointment_date": appointment.appointment_date.isoformat(),
            "reason_for_visit": appointment.reason_for_visit,
            "health_concerns": concerns,
        })

    response = JsonResponse({
        "appointments": data,
        "total_appointments": len(data),
    })

    response["Cache-Control"] = "no-store"
    return response

@login_required
def add_visit_instruction(request, pk):

    appointment = get_object_or_404(
        Appointment,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":
        form = VisitInstructionForm(request.POST)

        if form.is_valid():
            instruction = form.save(commit=False)

            instruction.appointment = appointment
            instruction.save()

            messages.success(
                request,
                "Your visit instruction was saved successfully!"
            )

            return redirect(
                "appointment_detail",
                pk=appointment.pk
            )

    else:
        form = VisitInstructionForm()

    return render(
        request,
        "appointments/visit_instruction_form.html",
        {
            "form": form,
            "appointment": appointment
        }
    )

from django.views.decorators.http import require_POST


@login_required
@require_POST
def toggle_instruction(request, pk):

    instruction = get_object_or_404(
        VisitInstruction,
        pk=pk,
        appointment__user=request.user
    )

    instruction.completed = not instruction.completed
    instruction.save(update_fields=["completed"])

    messages.success(
        request,
        "Instruction status updated!"
    )

    return redirect(
        "appointment_detail",
        pk=instruction.appointment.pk
    )


@login_required
def edit_health_concern(request, pk):

    concern = get_object_or_404(
        HealthConcern,
        pk=pk,
        appointment__user=request.user
    )

    if request.method == "POST":
        form = HealthConcernForm(
            request.POST,
            instance=concern
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Your health concern was updated successfully!"
            )

            return redirect(
                "appointment_detail",
                pk=concern.appointment.pk
            )

    else:
        form = HealthConcernForm(instance=concern)

    return render(
        request,
        "appointments/health_concern_form.html",
        {
            "form": form,
            "appointment": concern.appointment,
            "editing": True,
        }
    )

@login_required
def delete_health_concern(request, pk):

    concern = get_object_or_404(
        HealthConcern,
        pk=pk,
        appointment__user=request.user
    )

    if request.method == "POST":

        appointment_pk = concern.appointment.pk

        concern.delete()

        messages.success(
            request,
            "Your health concern was deleted successfully."
        )

        return redirect(
            "appointment_detail",
            pk=appointment_pk
        )

    return render(
        request,
        "appointments/health_concern_confirm_delete.html",
        {"concern": concern}
    )

@login_required
def edit_visit_instruction(request, pk):

    instruction = get_object_or_404(
        VisitInstruction,
        pk=pk,
        appointment__user=request.user
    )

    if request.method == "POST":
        form = VisitInstructionForm(
            request.POST,
            instance=instruction
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Your visit instruction was updated successfully!"
            )

            return redirect(
                "appointment_detail",
                pk=instruction.appointment.pk
            )

    else:
        form = VisitInstructionForm(instance=instruction)

    return render(
        request,
        "appointments/visit_instruction_form.html",
        {
            "form": form,
            "appointment": instruction.appointment,
            "editing": True,
        }
    )

@login_required
def symptom_history(request):

    concerns = HealthConcern.objects.filter(
        appointment__user=request.user
    ).select_related(
        "appointment"
    ).order_by(
        "appointment__appointment_date"
    )

    symptom_groups = {}

    for concern in concerns:

        symptom_name = concern.symptom.strip().lower()

        if symptom_name not in symptom_groups:
            symptom_groups[symptom_name] = {
                "name": concern.symptom.strip(),
                "records": [],
            }

        symptom_groups[symptom_name]["records"].append(
            concern
        )

    history = list(symptom_groups.values())

    history.sort(key=lambda item: item["name"].lower())

    return render(
        request,
        "appointments/symptom_history.html",
        {
            "history": history,
        }
    )

@login_required
def post_visit_dashboard(request):

    instructions = VisitInstruction.objects.filter(
        appointment__user=request.user
    ).select_related("appointment")

    # Overall statistics
    total_tasks = instructions.count()
    completed_tasks = instructions.filter(completed=True).count()
    remaining_tasks = total_tasks - completed_tasks

    completion_percentage = (
        round(completed_tasks / total_tasks * 100)
        if total_tasks > 0 else 0
    )

    # Get filter selections
    selected_category = request.GET.get("category", "")
    selected_status = request.GET.get("status", "")

    valid_categories = dict(VisitInstruction.CATEGORY_CHOICES)

    if selected_category in valid_categories:
        instructions = instructions.filter(
            category=selected_category
        )

    if selected_status == "completed":
        instructions = instructions.filter(completed=True)

    elif selected_status == "pending":
        instructions = instructions.filter(completed=False)

    # Organize instructions by category
    grouped_instructions = []

    for category_value, category_name in VisitInstruction.CATEGORY_CHOICES:

        category_tasks = list(
            instructions.filter(
                category=category_value
            ).order_by("due_date", "id")
        )

        if category_tasks:
            grouped_instructions.append({
                "name": category_name,
                "tasks": category_tasks,
            })

    return render(
        request,
        "appointments/post_visit_dashboard.html",
        {
            "grouped_instructions": grouped_instructions,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "remaining_tasks": remaining_tasks,
            "completion_percentage": completion_percentage,
            "categories": VisitInstruction.CATEGORY_CHOICES,
            "selected_category": selected_category,
            "selected_status": selected_status,
        }
    )
