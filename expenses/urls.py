from django.urls import path
from . import views

urlpatterns = [
    path('', views.expense_list, name='expense_list'),
    path('new/', views.expense_create, name='expense_create'),
    path('categories/', views.category_list, name='expense_category_list'),
]
