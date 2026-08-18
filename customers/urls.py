from django.urls import path
from . import views

urlpatterns = [
    path('', views.customer_list, name='customer_list'),
    path('new/', views.customer_create, name='customer_create'),
    path('edit/<hid:pk>/', views.customer_edit, name='customer_edit'),
    path('view/<hid:pk>/', views.customer_detail, name='customer_detail'),
    path('device/new/<hid:customer_id>/', views.device_create, name='device_create'),
    path('device/edit/<hid:pk>/', views.device_edit, name='device_edit'),
    path('api/devices/<hid:customer_id>/', views.customer_devices_api, name='customer_devices_api'),
]
