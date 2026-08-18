from django.urls import path
from apps.dashboards import views

urlpatterns = [
    path('', views.dashboard_router_view, name='dashboard_router'),
    path('dashboard/', views.dashboard_router_view, name='dashboard'),
    path('dashboard/superadmin/', views.superadmin_dashboard_view, name='superadmin_dashboard'),
    path('dashboard/server-admin/', views.serveradmin_dashboard_view, name='serveradmin_dashboard'),
    path('dashboard/manager/', views.manager_dashboard_view, name='manager_dashboard'),
    path('dashboard/hr/', views.hr_dashboard_view, name='hr_dashboard'),
    path('dashboard/dept-manager/', views.dept_manager_dashboard_view, name='dept_manager_dashboard'),
    path('dashboard/employee/', views.employee_dashboard_view, name='employee_dashboard'),
]
