from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from apps.attendance.models import Attendance, LeaveRequest
from apps.departments.models import Department, Branch
from apps.hierarchy.permissions import get_user_level
from apps.tasks.models import (
    Client,
    ClientAssignment,
    Task,
    TaskExtensionRequest,
    TaskSubmission,
)
from apps.recruitment.models import Candidate
from apps.tasks.models import Client
from apps.users.models import User

@login_required
def dashboard_router_view(request):
    """
    Intelligent router that directs the user to their role-dedicated dashboard.
    """
    user = request.user

    if user.role == User.Role.SUPERADMIN:
        return redirect('superadmin_dashboard')
    elif user.role == User.Role.SERVER_ADMIN:
        return redirect('serveradmin_dashboard')
    elif user.role == User.Role.MANAGER:
        return redirect('manager_dashboard')
    elif user.role == User.Role.HR:
        return redirect('hr_dashboard')
    elif user.role == User.Role.DEPT_MANAGER:
        return redirect('dept_manager_dashboard')
    else:
        return redirect('employee_dashboard')

@login_required
def superadmin_dashboard_view(request):
    total_users = User.objects.count()
    total_depts = Department.objects.count()
    total_branches = Branch.objects.count()
    
    # Role distribution breakdown
    role_counts = User.objects.values('role').annotate(count=Count('id')).order_by('-count')
    role_dict = {item['role']: item['count'] for item in role_counts}
    
    departments = Department.objects.annotate(
        members_count=Count('users', distinct=True),
        branches_count=Count('branches', distinct=True)
    ).all()

    recent_users = User.objects.select_related('department', 'branch').order_by('-id')[:8]
    unassigned_or_staff_users = User.objects.filter(role=User.Role.STAFF).select_related('department', 'branch').order_by('-id')[:6]

    pending_executive_leaves_count = LeaveRequest.objects.filter(
        status=LeaveRequest.Status.PENDING_SUPERADMIN_APPROVAL
    ).count()

    return render(request, 'dashboards/superadmin.html', {
        'total_users': total_users,
        'total_depts': total_depts,
        'total_branches': total_branches,
        'role_dict': role_dict,
        'departments': departments,
        'recent_users': recent_users,
        'unassigned_or_staff_users': unassigned_or_staff_users,
        'pending_executive_leaves_count': pending_executive_leaves_count,
        'all_roles_list': User.Role.choices,
        'page_title': 'Superadmin & Executive System Control',
    })

@login_required
def serveradmin_dashboard_view(request):
    total_users = User.objects.count()
    total_depts = Department.objects.count()
    total_branches = Branch.objects.count()

    role_counts = User.objects.values('role').annotate(count=Count('id')).order_by('-count')
    role_dict = {item['role']: item['count'] for item in role_counts}

    recent_users = User.objects.select_related('department', 'branch').order_by('-id')[:10]
    departments = Department.objects.annotate(
        members_count=Count('users', distinct=True),
        branches_count=Count('branches', distinct=True)
    ).all()

    return render(request, 'dashboards/serveradmin.html', {
        'total_users': total_users,
        'total_depts': total_depts,
        'total_branches': total_branches,
        'role_dict': role_dict,
        'recent_users': recent_users,
        'departments': departments,
        'page_title': 'Server & Infrastructure Administration Portal',
    })


@login_required
def manager_dashboard_view(request):
    user = request.user
    
    # Manager has dedicated branch creation & management capabilities
    dept = user.department
    if dept:
        managed_branches = Branch.objects.filter(department=dept)
        dept_members = User.objects.filter(department=dept).select_related('branch')
    else:
        managed_branches = Branch.objects.all()
        dept_members = User.objects.all().select_related('department', 'branch')

    dept_managers = dept_members.filter(role=User.Role.DEPT_MANAGER)
    staff_members = dept_members.exclude(role__in=[User.Role.SUPERADMIN, User.Role.SERVER_ADMIN, User.Role.MANAGER])
    
    all_depts = Department.objects.all()


    return render(request, 'dashboards/manager.html', {
        'managed_branches': managed_branches,
        'dept_members': dept_members,
        'dept_managers': dept_managers,
        'staff_members': staff_members,
        'current_dept': dept,
        'all_depts': all_depts,
        'page_title': 'Manager Operations & Branch Hub',
    })

@login_required
def hr_dashboard_view(request):
    today = timezone.localdate()
    total_employees = User.objects.exclude(role__in=[User.Role.SUPERADMIN, User.Role.SERVER_ADMIN]).count()
    
    departments = Department.objects.annotate(
        members_count=Count('users', distinct=True),
        branches_count=Count('branches', distinct=True)
    ).all()
    total_branches = Branch.objects.count()

    role_counts = User.objects.values('role').annotate(count=Count('id')).order_by('-count')
    role_dict = {item['role']: item['count'] for item in role_counts}

    recent_employees = User.objects.exclude(
        role__in=[User.Role.SUPERADMIN, User.Role.SERVER_ADMIN]
    ).select_related('department', 'branch').order_by('-id')[:10]

    # Department managers eligible for assignment review
    dept_managers = User.objects.filter(role=User.Role.DEPT_MANAGER).select_related('department', 'branch')

    # Live Attendance stats for today
    today_attendances = Attendance.objects.filter(date=today)
    present_today_count = today_attendances.filter(
        status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.HALF_DAY]
    ).count()
    late_today_count = today_attendances.filter(is_late=True).count()
    on_leave_today_count = today_attendances.filter(status=Attendance.Status.ON_LEAVE).count()

    # Pending Leave Governance
    pending_leaves = LeaveRequest.objects.filter(
        status__in=[
            LeaveRequest.Status.PENDING_DEPT_REVIEW,
            LeaveRequest.Status.PENDING_MANAGER_APPROVAL,
            LeaveRequest.Status.PENDING_SUPERADMIN_APPROVAL,
        ]
    ).select_related('user', 'user__department')
    pending_leaves_count = pending_leaves.count()
    recent_leaves = LeaveRequest.objects.select_related('user', 'user__department').order_by('-id')[:5]

    executives_count = role_dict.get(User.Role.EXECUTIVE, 0)
    staff_count = role_dict.get(User.Role.STAFF, 0)
    interns_count = role_dict.get(User.Role.INTERN, 0)
    managers_count = role_dict.get(User.Role.MANAGER, 0) + role_dict.get(User.Role.DEPT_MANAGER, 0)

    # Recruitment & Candidate Pipeline metrics
    candidates_to_be_called_count = Candidate.objects.filter(status=Candidate.Status.TO_BE_CALLED).count()
    candidates_called_count = Candidate.objects.filter(status=Candidate.Status.CALLED).count()
    candidates_approved_count = Candidate.objects.filter(status=Candidate.Status.APPROVED).count()
    candidates_interview_count = Candidate.objects.filter(status=Candidate.Status.INTERVIEW_SCHEDULED).count()
    total_candidates_count = Candidate.objects.count()
    recent_candidates = Candidate.objects.select_related('department', 'branch').order_by('-created_at')[:6]

    # External Customer Management metrics across departments
    total_customers_count = Client.objects.count()
    recent_customers = Client.objects.select_related('department', 'created_by').order_by('-created_at')[:6]
    department_customers_summary = Department.objects.annotate(
        client_count=Count('clients')
    ).filter(client_count__gt=0).order_by('-client_count')

    return render(request, 'dashboards/hr.html', {
        'total_employees': total_employees,
        'departments': departments,
        'total_branches': total_branches,
        'role_dict': role_dict,
        'executives_count': executives_count,
        'staff_count': staff_count,
        'interns_count': interns_count,
        'managers_count': managers_count,
        'recent_employees': recent_employees,
        'dept_managers': dept_managers,
        'today': today,
        'present_today_count': present_today_count,
        'late_today_count': late_today_count,
        'on_leave_today_count': on_leave_today_count,
        'pending_leaves_count': pending_leaves_count,
        'recent_leaves': recent_leaves,
        'candidates_to_be_called_count': candidates_to_be_called_count,
        'candidates_called_count': candidates_called_count,
        'candidates_approved_count': candidates_approved_count,
        'candidates_interview_count': candidates_interview_count,
        'total_candidates_count': total_candidates_count,
        'recent_candidates': recent_candidates,
        'total_customers_count': total_customers_count,
        'recent_customers': recent_customers,
        'department_customers_summary': department_customers_summary,
        'page_title': 'Human Resources Governance Center',
    })

@login_required
def dept_manager_dashboard_view(request):
    user = request.user
    dept = user.department
    branch = user.branch
    today = timezone.localdate()

    is_creative = bool(dept and 'creative' in dept.name.lower())
    is_it_club = bool(dept and 'it club' in dept.name.lower())

    # Dept Manager oversees Executives, Interns, and Staff
    subordinates = User.objects.filter(
        role__in=[User.Role.EXECUTIVE, User.Role.INTERN, User.Role.STAFF]
    )
    if dept:
        subordinates = subordinates.filter(department=dept)
    if branch:
        subordinates = subordinates.filter(branch=branch)
    
    subordinates = subordinates.select_related('department', 'branch').order_by('role', 'first_name')

    # Attach today's attendance status to each subordinate
    today_attendances = Attendance.objects.filter(date=today)
    if dept:
        today_attendances = today_attendances.filter(user__department=dept)
    if branch:
        today_attendances = today_attendances.filter(user__branch=branch)

    attendance_map = {att.user_id: att for att in today_attendances}
    for sub in subordinates:
        sub.today_attendance = attendance_map.get(sub.id)

    total_subordinates = subordinates.count()
    executives_count = subordinates.filter(role=User.Role.EXECUTIVE).count()
    interns_count = subordinates.filter(role=User.Role.INTERN).count()
    staff_count = subordinates.filter(role=User.Role.STAFF).count()

    present_today_count = today_attendances.filter(
        status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.HALF_DAY]
    ).count()
    late_today_count = today_attendances.filter(is_late=True).count()
    on_leave_today_count = today_attendances.filter(status=Attendance.Status.ON_LEAVE).count()

    clients_count = 0
    recent_clients = []
    client_assignments_count = 0
    recent_client_assignments = []
    active_tasks_count = 0
    total_tasks_count = 0
    recent_tasks = []
    pending_submissions_count = 0
    pending_extensions_count = 0
    pending_leaves_count = 0
    pending_mgr_client_reviews = 0
    pending_leaves = []

    if dept:
        pending_leaves_qs = LeaveRequest.objects.filter(
            user__department=dept,
            status=LeaveRequest.Status.PENDING_DEPT_REVIEW
        ).select_related('user', 'user__branch').order_by('-created_at')
        pending_leaves_count = pending_leaves_qs.count()
        pending_leaves = pending_leaves_qs[:5]

        if is_creative:
            clients_count = Client.objects.filter(department=dept).count()
            recent_clients = Client.objects.filter(department=dept).order_by('-created_at')[:6]
            client_assignments_count = ClientAssignment.objects.filter(client__department=dept).count()
            recent_client_assignments = ClientAssignment.objects.filter(
                client__department=dept
            ).select_related('client', 'branch', 'executive', 'delegated_member').order_by('-created_at')[:6]

            active_tasks_count = Task.objects.filter(department=dept, status=Task.Status.ACTIVE).count()
            total_tasks_count = Task.objects.filter(department=dept).count()
            recent_tasks = Task.objects.filter(department=dept).select_related(
                'branch', 'assigned_to', 'created_by'
            ).order_by('-created_at')[:6]

            pending_submissions_count = TaskSubmission.objects.filter(
                task__department=dept,
                review_status=TaskSubmission.ReviewStatus.PENDING
            ).count()

            pending_extensions_count = TaskExtensionRequest.objects.filter(
                task__department=dept,
                status=TaskExtensionRequest.Status.PENDING
            ).count()

            pending_mgr_client_reviews = ClientAssignment.objects.filter(
                client__department=dept,
                status=ClientAssignment.Status.UNDER_DEPT_MANAGER_REVIEW
            ).count()

    department_branches = []
    if dept:
        department_branches = list(Branch.objects.filter(department=dept).annotate(
            users_count=Count('users', distinct=True)
        ).order_by('name'))
        for br in department_branches:
            br.executives_cnt = br.users.filter(role=User.Role.EXECUTIVE).count()
            br.staff_cnt = br.users.filter(role=User.Role.STAFF).count()
            br.interns_cnt = br.users.filter(role=User.Role.INTERN).count()

    dept_customers = Client.objects.filter(department=dept).order_by('-created_at') if dept else Client.objects.none()
    dept_customers_count = dept_customers.count()
    recent_dept_customers = dept_customers[:6]

    if is_it_club:
        page_title = "IT Club Operations & Engineering Command Center"
    elif is_creative:
        page_title = "Creative Operations Control Center"
    else:
        page_title = f"{dept.name if dept else 'Department'} Management Hub"

    total_action_required = pending_submissions_count + pending_extensions_count + pending_leaves_count + pending_mgr_client_reviews

    return render(request, 'dashboards/dept_manager.html', {
        'subordinates': subordinates,
        'total_subordinates': total_subordinates,
        'executives_count': executives_count,
        'interns_count': interns_count,
        'staff_count': staff_count,
        'current_dept': dept,
        'current_branch': branch,
        'is_creative': is_creative,
        'is_it_club': is_it_club,
        'today': today,
        'present_today_count': present_today_count,
        'late_today_count': late_today_count,
        'on_leave_today_count': on_leave_today_count,
        'department_branches': department_branches,
        'clients_count': clients_count,
        'recent_clients': recent_clients,
        'client_assignments_count': client_assignments_count,
        'recent_client_assignments': recent_client_assignments,
        'active_tasks_count': active_tasks_count,
        'total_tasks_count': total_tasks_count,
        'recent_tasks': recent_tasks,
        'pending_submissions_count': pending_submissions_count,
        'pending_extensions_count': pending_extensions_count,
        'pending_leaves_count': pending_leaves_count,
        'pending_leaves': pending_leaves,
        'pending_mgr_client_reviews': pending_mgr_client_reviews,
        'total_action_required': total_action_required,
        'dept_customers_count': dept_customers_count,
        'recent_dept_customers': recent_dept_customers,
        'page_title': page_title,
    })

@login_required
def employee_dashboard_view(request):
    user = request.user
    dept = user.department
    branch = user.branch

    # Company departments for company overview section
    company_departments = Department.objects.prefetch_related('branches').annotate(
        members_count=Count('users', distinct=True)
    ).order_by('name')

    # Department leadership contact point
    dept_manager = None
    if dept:
        dept_manager = User.objects.filter(
            department=dept,
            role__in=[User.Role.DEPT_MANAGER, User.Role.MANAGER]
        ).first()

    # HR Representative contact
    hr_rep = User.objects.filter(role=User.Role.HR).first()

    teammates = []
    if dept:
        teammates = User.objects.filter(department=dept).exclude(id=user.id).select_related('branch')[:8]

    # Creative tasks for this employee's branch
    from apps.tasks.models import Task
    branch_tasks = Task.objects.none()
    if dept:
        if branch:
            branch_tasks = Task.objects.filter(department=dept).filter(
                Q(branch=branch) | Q(branch__isnull=True)
            ).select_related('created_by', 'branch', 'assigned_to').prefetch_related('attachments').order_by('-created_at')
        else:
            branch_tasks = Task.objects.filter(department=dept, branch__isnull=True).select_related('created_by', 'branch', 'assigned_to').prefetch_related('attachments').order_by('-created_at')

    # Client assignments for this employee
    executive_client_assignments = []
    member_client_assignments = []
    pending_exec_reviews_count = 0

    if user.role == User.Role.EXECUTIVE:
        executive_client_assignments = ClientAssignment.objects.filter(
            Q(executive=user) | Q(branch=branch)
        ).select_related('client', 'branch', 'assigned_by', 'delegated_member').order_by('-created_at')
        pending_exec_reviews_count = ClientAssignment.objects.filter(
            executive=user,
            status=ClientAssignment.Status.UNDER_EXECUTIVE_REVIEW
        ).count()
    else:
        member_client_assignments = ClientAssignment.objects.filter(
            delegated_member=user
        ).select_related('client', 'branch', 'assigned_by', 'executive').order_by('-created_at')

    return render(request, 'dashboards/employee.html', {
        'user_profile': user,
        'department': dept,
        'branch': branch,
        'dept_manager': dept_manager,
        'hr_rep': hr_rep,
        'company_departments': company_departments,
        'teammates': teammates,
        'branch_tasks': branch_tasks,
        'executive_client_assignments': executive_client_assignments,
        'member_client_assignments': member_client_assignments,
        'pending_exec_reviews_count': pending_exec_reviews_count,
        'page_title': f'Employee Portal: {user.get_full_name() or user.username}',
    })

