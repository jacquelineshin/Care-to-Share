
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
    path("instructions/<int:pk>/toggle/", views.toggle_instruction, name="toggle_instruction"
),
]
