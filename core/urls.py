from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('settings/', views.settings_view, name='settings_view'),
    path('api/auth/session-ping/', views.session_ping_api, name='session_ping_api'),
    path('api/search/', views.global_search_api, name='global_search_api'),
    path('api/reports-data/', views.reports_data_api, name='reports_data_api'),
    path('reports/', views.reports_home, name='reports_home'),
    path('reports/daily/', views.daily_report, name='daily_report'),
    path('reports/profit-loss/', views.monthly_profit_loss, name='monthly_profit_loss'),
    path('audit-logs/', views.audit_log_list, name='audit_log_list'),
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('404/', views.custom_404_view, name='page_404'),
]
