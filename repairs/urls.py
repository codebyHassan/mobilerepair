from django.urls import path
from . import views

urlpatterns = [
    path('', views.repair_list, name='repair_list'),
    path('intake/', views.repair_intake, name='repair_intake'),
    path('new/', views.repair_create, name='repair_create'),
    path('view/<hid:pk>/', views.repair_detail, name='repair_detail'),
    path('lifecycle/<hid:pk>/', views.repair_lifecycle, name='repair_lifecycle'),
    path('lifecycle/<hid:pk>/stage/<str:stage_code>/', views.repair_lifecycle, name='repair_lifecycle_stage'),
    path('status/<hid:pk>/', views.change_status, name='change_status'),
    path('diagnosis/<hid:pk>/', views.update_diagnosis, name='update_diagnosis'),
    path('estimate/<hid:pk>/', views.update_estimate, name='update_estimate'),
    path('technicians/', views.technician_list, name='technician_list'),
    path('technicians/new/', views.technician_create, name='technician_create'),
    path('technicians/edit/<hid:pk>/', views.technician_edit, name='technician_edit'),
    path('commissions/', views.technician_commissions, name='technician_commissions'),
    path('ess/', views.technician_ess_dashboard, name='technician_ess_dashboard'),
    path('intake-slip/<hid:pk>/image/', views.repair_intake_image, name='repair_intake_image'),
    path('diagnosis-slip/<hid:pk>/', views.diagnosis_thermal_slip, name='diagnosis_thermal_slip'),
    path('diagnosis-slip/<hid:pk>/image/', views.diagnosis_image, name='diagnosis_image'),
]
