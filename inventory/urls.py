from django.urls import path
from . import views

urlpatterns = [
    path('', views.part_list, name='part_list'),
    path('new/', views.part_create, name='part_create'),
    path('edit/<hid:pk>/', views.part_edit, name='part_edit'),
    path('view/<hid:pk>/', views.part_detail, name='part_detail'),
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/new/', views.supplier_create, name='supplier_create'),
    path('suppliers/<hid:pk>/', views.supplier_detail, name='supplier_detail'),
    path('suppliers/<hid:pk>/pay/', views.supplier_payment_create, name='supplier_payment_create'),
    path('transaction/new/<hid:part_id>/', views.transaction_create, name='transaction_create'),
    path('use-part/<hid:job_id>/', views.use_part, name='use_part'),
    path('remove-part/<hid:repair_part_id>/', views.remove_part, name='remove_part'),
]
