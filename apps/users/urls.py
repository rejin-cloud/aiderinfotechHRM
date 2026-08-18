from django.urls import path
from apps.users import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('quick-switch/<int:user_id>/', views.quick_switch_user_view, name='quick_switch_user'),
    path('profile/', views.profile_view, name='profile'),
    path('users/', views.user_list_view, name='user_list'),
    path('users/new/', views.user_create_view, name='user_create'),
    path('users/assign/', views.user_assign_view, name='assign_employee'),
    path('users/<int:user_id>/assign/', views.user_assign_view, name='assign_specific_employee'),
    path('users/<int:pk>/', views.user_detail_view, name='user_detail'),
    path('users/<int:pk>/edit/', views.user_update_view, name='user_update'),
    path('users/<int:pk>/delete/', views.user_delete_view, name='user_delete'),
    path('api/branches/', views.get_branches_by_department_json, name='api_branches_by_department'),
]
