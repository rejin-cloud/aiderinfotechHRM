from django.urls import path
from apps.departments import views

urlpatterns = [
    path('departments/', views.department_list_view, name='department_list'),
    path('departments/new/', views.department_create_view, name='department_create'),
    path('departments/<int:pk>/', views.department_detail_view, name='department_detail'),
    path('departments/<int:pk>/edit/', views.department_update_view, name='department_update'),
    path('departments/<int:pk>/delete/', views.department_delete_view, name='department_delete'),
    
    # Branches
    path('branches/new/', views.branch_create_view, name='branch_create'),
    path('branches/<int:pk>/', views.branch_detail_view, name='branch_detail'),
    path('branches/<int:pk>/edit/', views.branch_update_view, name='branch_update'),
    path('branches/<int:pk>/delete/', views.branch_delete_view, name='branch_delete'),
]
