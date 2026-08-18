from django.urls import path
from apps.attendance import views

urlpatterns = [
    path('', views.attendance_hub_view, name='attendance_hub'),
    path('check-in/', views.check_in_view, name='attendance_check_in'),
    path('check-out/', views.check_out_view, name='attendance_check_out'),
    path('my-history/', views.my_attendance_history_view, name='my_attendance_history'),
    path('department-roster/', views.department_attendance_roster_view, name='department_attendance_roster'),

    # Leave Management
    path('leave/apply/', views.leave_apply_view, name='leave_apply'),
    path('leave/my-leaves/', views.my_leaves_view, name='my_leaves'),
    path('leave/<int:leave_id>/cancel/', views.cancel_leave_view, name='cancel_leave'),

    # Multi-Stage Approval Workflow
    path('leave/dept-reviews/', views.dept_manager_leave_reviews_view, name='dept_manager_leave_reviews'),
    path('leave/dept-reviews/<int:leave_id>/', views.dept_manager_review_action_view, name='dept_manager_review_action'),
    path('leave/manager-approvals/', views.manager_leave_approvals_view, name='manager_leave_approvals'),
    path('leave/manager-approvals/<int:leave_id>/', views.manager_decision_action_view, name='manager_decision_action'),

    # Monthly Reports & Exports (Level 2+ Restricted)
    path('reports/', views.monthly_reports_view, name='attendance_monthly_reports'),
    path('reports/export/excel/', views.export_monthly_excel_view, name='attendance_export_excel'),
    path('reports/export/pdf/', views.export_monthly_pdf_view, name='attendance_export_pdf'),
]
