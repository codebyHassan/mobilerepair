from django.urls import path
from . import views

urlpatterns = [
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoice/<hid:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoice/<hid:pk>/pdf/', views.invoice_pdf, name='invoice_pdf'),
    path('invoice/<hid:pk>/image/', views.invoice_image, name='invoice_image'),
    path('invoice/print/<hid:pk>/', views.invoice_print, name='invoice_print'),
    path('payments/', views.payment_list, name='payment_list'),
    path('payment/new/<hid:invoice_id>/', views.payment_create, name='payment_create'),
]
