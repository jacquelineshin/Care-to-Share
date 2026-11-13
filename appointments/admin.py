
from django.contrib import admin
from .models import Appointment, HealthConcern, VisitInstruction, EducationalResource

admin.site.register(Appointment)
admin.site.register(HealthConcern)
admin.site.register(VisitInstruction)
admin.site.register(EducationalResource)
