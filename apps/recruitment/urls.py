from django.urls import path
from . import views

urlpatterns = [
    path('candidates/', views.candidate_list_view, name='candidate_list'),
    path('candidates/approved/', views.candidate_approved_list_view, name='candidate_approved_list'),
    path('candidates/add/', views.candidate_create_view, name='candidate_create'),
    path('candidates/<int:candidate_id>/', views.candidate_detail_view, name='candidate_detail'),
    path('candidates/<int:candidate_id>/edit/', views.candidate_edit_view, name='candidate_edit'),
    path('candidates/<int:candidate_id>/call/', views.candidate_mark_called_view, name='candidate_mark_called'),
    path('candidates/<int:candidate_id>/decide/', views.candidate_decide_view, name='candidate_decide'),
    path('candidates/<int:candidate_id>/interview/', views.candidate_schedule_interview_view, name='candidate_schedule_interview'),
    path('candidates/<int:candidate_id>/interview-outcome/', views.candidate_interview_outcome_view, name='candidate_interview_outcome'),
    path('candidates/<int:candidate_id>/delete/', views.candidate_delete_view, name='candidate_delete'),
]
