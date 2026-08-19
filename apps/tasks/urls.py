from django.urls import path
from apps.tasks import views

urlpatterns = [
    path('', views.task_list_view, name='task_list'),
    path('create/', views.task_create_view, name='task_create'),
    path('assign/', views.task_assign_view, name='task_assign'),
    path('assign/<int:task_id>/', views.task_assign_view, name='task_assign_specific'),
    path('requests/', views.manager_extension_requests_view, name='manager_extension_requests'),
    path('requests/<int:request_id>/review/', views.manager_extension_review_view, name='manager_extension_review'),
    path('api/branch-members/<int:branch_id>/', views.branch_members_api, name='branch_members_api'),
    path('<int:task_id>/', views.task_detail_view, name='task_detail'),
    path('<int:task_id>/complete/', views.task_complete_view, name='task_complete'),
    path('<int:task_id>/review-submission/', views.manager_submission_review_view, name='manager_submission_review'),
    path('<int:task_id>/review-submission/<int:submission_id>/', views.manager_submission_review_view, name='manager_submission_review_specific'),
    path('<int:task_id>/request-extension/', views.task_request_extension_view, name='task_request_extension'),
    path('<int:task_id>/edit/', views.task_edit_view, name='task_edit'),
    path('<int:task_id>/delete/', views.task_delete_view, name='task_delete'),
    path('attachments/<int:attachment_id>/delete/', views.attachment_delete_view, name='attachment_delete'),
    
    # Creative Department Client Management
    path('clients/', views.client_list_view, name='client_list'),
    path('clients/add/', views.client_create_view, name='client_create'),
    path('clients/assign/', views.client_assign_view, name='client_assign_general'),
    path('clients/<int:client_id>/', views.client_detail_view, name='client_detail'),
    path('clients/<int:client_id>/assign/', views.client_assign_view, name='client_assign'),
    path('clients/<int:client_id>/edit/', views.client_edit_view, name='client_edit'),
    path('clients/<int:client_id>/delete/', views.client_delete_view, name='client_delete'),
    path('clients/assignments/all/', views.executive_client_assignments_view, name='executive_client_assignments'),
    path('clients/assignments/<int:assignment_id>/delegate/', views.executive_client_delegate_view, name='executive_client_delegate'),
    path('api/branch-executives/<int:branch_id>/', views.branch_executives_api, name='branch_executives_api'),
]
