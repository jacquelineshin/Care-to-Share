
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("appointments/<int:pk>/", views.appointment_detail, name="appointment_detail"),
    path("appointments/new/", views.create_appointment, name="create_appointment" ),
    path("appointments/<int:pk>/edit/", views.edit_appointment, name="edit_appointment"),
    path("appointments/<int:pk>/delete/", views.delete_appointment, name="delete_appointment"),
    path("appointments/<int:pk>/concerns/new/", views.add_health_concern, name="add_health_concern"),
    path("register/", views.register, name="register"),
    path("api/appointments/", views.appointments_api, name="appointments_api"),
    path("appointments/<int:pk>/instructions/new/", views.add_visit_instruction, name="add_visit_instruction"),
    path("instructions/<int:pk>/toggle/", views.toggle_instruction, name="toggle_instruction"),
    path("appointments/<int:pk>/summary/", views.pre_visit_summary, name="pre_visit_summary"),
    path("concerns/<int:pk>/edit/", views.edit_health_concern, name="edit_health_concern"),
    path("concerns/<int:pk>/resources/", views.recommended_resources, name="recommended_resources"),
    path("concerns/<int:pk>/delete/", views.delete_health_concern, name="delete_health_concern"),
    path("instructions/<int:pk>/edit/", views.edit_visit_instruction, name="edit_visit_instruction"),
    path("instructions/<int:pk>/delete/", views.delete_visit_instruction, name="delete_visit_instruction"),
    path("symptom-history/", views.symptom_history, name="symptom_history"),
    path("post-visit-plan/", views.post_visit_dashboard, name="post_visit_dashboard"),
]
