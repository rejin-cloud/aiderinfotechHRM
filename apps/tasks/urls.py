from django.urls import path
from apps.tasks import views

urlpatterns = [
    path('', views.task_list_view, name='task_list'),
    path('create/', views.task_create_view, name='task_create'),
    path('assign/', views.task_assign_view, name='task_assign'),
    path('assign/<int:task_id>/', views.task_assign_view, name='task_assign_specific'),
    path('api/branch-members/<int:branch_id>/', views.branch_members_api, name='branch_members_api'),
    path('<int:task_id>/', views.task_detail_view, name='task_detail'),
    path('<int:task_id>/edit/', views.task_edit_view, name='task_edit'),
    path('<int:task_id>/delete/', views.task_delete_view, name='task_delete'),
    path('attachments/<int:attachment_id>/delete/', views.attachment_delete_view, name='attachment_delete'),
]
