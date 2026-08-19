from django.urls import path
from apps.attendance import views

urlpatterns = [
    path('', views.attendance_hub_view, name='attendance_hub'),
    path('check-in/', views.check_in_view, name='attendance_check_in'),
    path('check-out/', views.check_out_view, name='attendance_check_out'),
    path('my-history/', views.my_attendance_history_view, name='my_attendance_history'),
    path('department-roster/', views.department_attendance_roster_view, name='department_attendance_roster'),

    # Leave Management (Standard Employees below Manager level)
    path('leave/apply/', views.leave_apply_view, name='leave_apply'),
    path('leave/my-leaves/', views.my_leaves_view, name='my_leaves'),
    path('leave/<int:leave_id>/cancel/', views.cancel_leave_view, name='cancel_leave'),

    # Separate Dedicated Leave Management for Server Admin, HR, and Manager level personals
    path('leave/executive-apply/', views.executive_leave_apply_view, name='executive_leave_apply'),

    # Multi-Stage Approval Workflow (Staff -> Dept Manager -> General Manager)
    path('leave/dept-reviews/', views.dept_manager_leave_reviews_view, name='dept_manager_leave_reviews'),
    path('leave/dept-reviews/<int:leave_id>/', views.dept_manager_review_action_view, name='dept_manager_review_action'),
    path('leave/manager-approvals/', views.manager_leave_approvals_view, name='manager_leave_approvals'),
    path('leave/manager-approvals/<int:leave_id>/', views.manager_decision_action_view, name='manager_decision_action'),

    # Super Admin Executive Leave Review & Approval Portal
    path('leave/superadmin-approvals/', views.superadmin_leave_approvals_view, name='superadmin_leave_approvals'),
    path('leave/superadmin-approvals/<int:leave_id>/', views.superadmin_decision_action_view, name='superadmin_decision_action'),

    # Monthly Reports & Exports (Level 2+ Restricted)
    path('reports/', views.monthly_reports_view, name='attendance_monthly_reports'),
    path('reports/export/excel/', views.export_monthly_excel_view, name='attendance_export_excel'),
    path('reports/export/pdf/', views.export_monthly_pdf_view, name='attendance_export_pdf'),
]
