import calendar
from datetime import date, datetime, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.attendance.exporters import generate_monthly_attendance_excel, generate_monthly_attendance_pdf
from apps.attendance.forms import (
    CheckInForm,
    CheckOutForm,
    DeptManagerReviewForm,
    ExecutiveLeaveApplicationForm,
    LeaveApplicationForm,
    ManagerFinalDecisionForm,
    MonthlyReportFilterForm,
    SuperadminLeaveDecisionForm,
)
from apps.attendance.models import Attendance, LeaveRequest
from apps.attendance.permissions import (
    can_approve_executive_leave,
    can_approve_leave_final,
    can_log_attendance,
    can_review_leave_dept_level,
    can_view_monthly_reports,
    can_view_user_attendance,
    is_executive_leave_applicant,
)
from apps.departments.models import Department
from apps.hierarchy.permissions import get_user_level
from apps.users.models import User


# =====================================================================
# 1. Attendance Hub & Clock-In / Clock-Out
# =====================================================================

@login_required
def attendance_hub_view(request):
    """
    Main attendance hub.
    - Non-superadmins see their daily check-in / check-out widget.
    - Superadmin sees exemption banner and quick navigation to team reports.
    - Displays today's status, monthly metrics summary, and quick links.
    """
    today = timezone.localdate()
    user = request.user
    is_superadmin = (user.role == User.Role.SUPERADMIN)

    today_record = None
    if not is_superadmin:
        today_record = Attendance.objects.filter(user=user, date=today).first()

    # User's current month statistics
    current_month = today.month
    current_year = today.year
    user_monthly_records = Attendance.objects.filter(
        user=user,
        date__year=current_year,
        date__month=current_month
    )

    stats = {
        'present_days': user_monthly_records.filter(models.Q(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.HALF_DAY]) | models.Q(is_late=True)).count(),
        'on_time_days': user_monthly_records.filter(status=Attendance.Status.PRESENT, is_late=False).count(),
        'late_days': user_monthly_records.filter(models.Q(status=Attendance.Status.LATE) | models.Q(is_late=True)).count(),
        'half_days': user_monthly_records.filter(status=Attendance.Status.HALF_DAY).count(),
        'leave_days': user_monthly_records.filter(status=Attendance.Status.ON_LEAVE).count(),
        'absent_days': user_monthly_records.filter(status=Attendance.Status.ABSENT).count(),
        'total_work_minutes': sum(r.work_duration_minutes for r in user_monthly_records),
    }
    stats['total_work_hours'] = round(stats['total_work_minutes'] / 60, 1)

    # Active leave applications
    my_recent_leaves = LeaveRequest.objects.filter(user=user)[:5]

    # Management queue counts
    pending_dept_reviews_count = 0
    pending_manager_approvals_count = 0
    pending_superadmin_approvals_count = 0

    if is_superadmin:
        pending_superadmin_approvals_count = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.PENDING_SUPERADMIN_APPROVAL
        ).count()

    if user.role == User.Role.DEPT_MANAGER and user.department:
        pending_dept_reviews_count = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.PENDING_DEPT_REVIEW,
            user__department=user.department
        ).count()
    elif get_user_level(user) <= 2:
        pending_dept_reviews_count = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.PENDING_DEPT_REVIEW
        ).count()

    if get_user_level(user) <= 2:
        pending_manager_approvals_count = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.PENDING_MANAGER_APPROVAL
        ).count()

    checkin_form = CheckInForm()
    checkout_form = CheckOutForm()

    context = {
        'today': today,
        'today_record': today_record,
        'is_superadmin': is_superadmin,
        'stats': stats,
        'my_recent_leaves': my_recent_leaves,
        'pending_dept_reviews_count': pending_dept_reviews_count,
        'pending_manager_approvals_count': pending_manager_approvals_count,
        'pending_superadmin_approvals_count': pending_superadmin_approvals_count,
        'can_view_reports': can_view_monthly_reports(user),
        'checkin_form': checkin_form,
        'checkout_form': checkout_form,
        'current_month_name': calendar.month_name[current_month],
    }
    return render(request, 'attendance/hub.html', context)


@login_required
def check_in_view(request):
    """Handles 1-click check-in for non-superadmin employees."""
    if not can_log_attendance(request.user):
        messages.info(request, "Superadmin accounts are exempted from daily attendance tracking.")
        return redirect('attendance_hub')

    if request.method == 'POST':
        today = timezone.localdate()
        now = timezone.now()
        record, created = Attendance.objects.get_or_create(
            user=request.user,
            date=today,
            defaults={'check_in': now}
        )

        if not created and record.check_in:
            messages.warning(request, f"You have already checked in today at {timezone.localtime(record.check_in).strftime('%I:%M %p')}.")
        else:
            form = CheckInForm(request.POST)
            notes = form.cleaned_data.get('notes') if form.is_valid() else ''
            record.check_in = now
            record.check_in_notes = notes
            record.calculate_duration_and_status()
            record.save()

            if record.is_late or record.status == Attendance.Status.LATE:
                status_msg = "Present & Late"
            else:
                status_msg = "Present (On-Time)"
            messages.success(
                request,
                f"Clock-in successful at {timezone.localtime(now).strftime('%I:%M %p')} IST! Attendance registered as {status_msg}."
            )

    return redirect('attendance_hub')


@login_required
def check_out_view(request):
    """Handles check-out for today's active attendance session."""
    if not can_log_attendance(request.user):
        messages.info(request, "Superadmin accounts are exempted from daily attendance tracking.")
        return redirect('attendance_hub')

    if request.method == 'POST':
        today = timezone.localdate()
        now = timezone.now()
        record = Attendance.objects.filter(user=request.user, date=today).first()

        if not record or not record.check_in:
            messages.error(request, "Cannot check out: You haven't checked in yet today.")
        elif record.check_out:
            messages.warning(request, f"You have already checked out today at {timezone.localtime(record.check_out).strftime('%I:%M %p')}.")
        else:
            form = CheckOutForm(request.POST)
            notes = form.cleaned_data.get('notes') if form.is_valid() else ''
            record.check_out = now
            if notes:
                record.check_out_notes = notes
            record.calculate_duration_and_status()
            record.save()

            messages.success(
                request,
                f"Clock-out confirmed at {timezone.localtime(now).strftime('%I:%M %p')}! Total work time: {record.formatted_duration}."
            )

    return redirect('attendance_hub')


# =====================================================================
# 2. Attendance History & Department Rosters
# =====================================================================

@login_required
def my_attendance_history_view(request):
    """Personal monthly attendance logs for the logged-in employee."""
    user = request.user
    today = timezone.localdate()

    selected_year = int(request.GET.get('year', today.year))
    selected_month = int(request.GET.get('month', today.month))

    records = Attendance.objects.filter(
        user=user,
        date__year=selected_year,
        date__month=selected_month
    ).order_by('-date')

    # Month metrics
    stats = {
        'present': records.filter(models.Q(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.HALF_DAY]) | models.Q(is_late=True)).count(),
        'on_time': records.filter(status=Attendance.Status.PRESENT, is_late=False).count(),
        'late': records.filter(models.Q(status=Attendance.Status.LATE) | models.Q(is_late=True)).count(),
        'half_day': records.filter(status=Attendance.Status.HALF_DAY).count(),
        'on_leave': records.filter(status=Attendance.Status.ON_LEAVE).count(),
        'absent': records.filter(status=Attendance.Status.ABSENT).count(),
        'total_hours': round(sum(r.work_duration_minutes for r in records) / 60, 1),
    }

    # Month list for navigation dropdown
    months = [(m, calendar.month_name[m]) for m in range(1, 13)]
    years = range(today.year - 2, today.year + 2)

    context = {
        'records': records,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'selected_month_name': calendar.month_name[selected_month],
        'months': months,
        'years': years,
        'stats': stats,
    }
    return render(request, 'attendance/my_history.html', context)


@login_required
def department_attendance_roster_view(request):
    """
    Roster view showing attendance for team members:
    - Dept Managers (Level 3): ONLY sees personnel in their own department.
    - Managers / HR / Level 1: Can filter across departments or view full organization.
    - Level 4: Access Denied (redirected).
    """
    user = request.user
    user_lvl = get_user_level(user)

    if user_lvl > 3:
        messages.error(request, "Access restricted: Staff members can view only their personal attendance record.")
        return redirect('my_attendance_history')

    today = timezone.localdate()
    selected_date_str = request.GET.get('date', today.strftime('%Y-%m-%d'))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = today

    # Filter base user queryset based on role scope
    if user.role == User.Role.DEPT_MANAGER:
        if not user.department:
            messages.warning(request, "You are not assigned to a department yet.")
            return redirect('attendance_hub')
        target_users = User.objects.filter(
            department=user.department
        ).exclude(role=User.Role.SUPERADMIN)
        current_dept = user.department
        dept_choices = None
    elif user.role == User.Role.MANAGER and user.department:
        dept_id = request.GET.get('department')
        if dept_id:
            target_users = User.objects.filter(department_id=dept_id).exclude(role=User.Role.SUPERADMIN)
            current_dept = Department.objects.filter(id=dept_id).first()
        else:
            target_users = User.objects.filter(department=user.department).exclude(role=User.Role.SUPERADMIN)
            current_dept = user.department
        dept_choices = Department.objects.all()
    else:
        # HR & Level 1
        dept_id = request.GET.get('department')
        if dept_id:
            target_users = User.objects.filter(department_id=dept_id).exclude(role=User.Role.SUPERADMIN)
            current_dept = Department.objects.filter(id=dept_id).first()
        else:
            target_users = User.objects.exclude(role=User.Role.SUPERADMIN)
            current_dept = None
        dept_choices = Department.objects.all()

    # Search filter
    search_q = request.GET.get('q', '').strip()
    if search_q:
        target_users = target_users.filter(
            username__icontains=search_q
        ) | target_users.filter(
            first_name__icontains=search_q
        ) | target_users.filter(
            last_name__icontains=search_q
        ) | target_users.filter(
            employee_id__icontains=search_q
        )

    # Fetch attendance records for selected date
    attendances = Attendance.objects.filter(
        user__in=target_users,
        date=selected_date
    )
    att_map = {a.user_id: a for a in attendances}

    # Build roster rows
    roster_rows = []
    present_cnt = 0
    late_cnt = 0
    leave_cnt = 0
    absent_cnt = 0

    for u in target_users:
        record = att_map.get(u.id)
        if record:
            if record.status in [Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.HALF_DAY] or record.is_present:
                present_cnt += 1
            if record.status == Attendance.Status.LATE or record.is_late:
                late_cnt += 1
            elif record.status == Attendance.Status.ON_LEAVE:
                leave_cnt += 1
            elif record.status == Attendance.Status.ABSENT:
                absent_cnt += 1
        else:
            absent_cnt += 1

        roster_rows.append({
            'user': u,
            'record': record,
        })

    context = {
        'selected_date': selected_date,
        'roster_rows': roster_rows,
        'current_dept': current_dept,
        'dept_choices': dept_choices,
        'search_q': search_q,
        'total_employees': len(roster_rows),
        'present_cnt': present_cnt,
        'late_cnt': late_cnt,
        'leave_cnt': leave_cnt,
        'absent_cnt': absent_cnt,
    }
    return render(request, 'attendance/department_roster.html', context)


# =====================================================================
# 3. Leave Application & Management Workflow
# =====================================================================

@login_required
def leave_apply_view(request):
    """
    Standard Leave Application for employees below manager level (Staff, Intern, Executive).
    If Super Admin visits: informed they do not require leave.
    If Server Admin, HR, or Manager visits: redirected to their dedicated Executive Leave portal.
    """
    if request.user.role == User.Role.SUPERADMIN:
        messages.info(request, "Super Admin accounts represent executive ownership and do not submit leave applications.")
        return redirect('superadmin_leave_approvals')

    if is_executive_leave_applicant(request.user):
        return redirect('executive_leave_apply')

    if request.method == 'POST':
        form = LeaveApplicationForm(request.POST)
        if form.is_valid():
            leave_req = form.save(commit=False)
            leave_req.user = request.user
            leave_req.status = LeaveRequest.Status.PENDING_DEPT_REVIEW
            leave_req.save()

            messages.success(
                request,
                f"Leave application for {leave_req.get_leave_type_display()} ({leave_req.start_date} to {leave_req.end_date}) submitted successfully! "
                f"Your request has been routed to your Department Manager for review."
            )
            return redirect('my_leaves')
    else:
        form = LeaveApplicationForm()

    return render(request, 'attendance/leave_apply.html', {'form': form})


@login_required
def executive_leave_apply_view(request):
    """
    Separate Dedicated Leave Application Portal for Server Admin, HR, Manager, and Department Managers.
    All applications submitted here are routed directly to the Super Admin for review and approval.
    """
    if request.user.role == User.Role.SUPERADMIN:
        messages.info(request, "Super Admin accounts represent executive ownership and do not submit leave applications.")
        return redirect('superadmin_leave_approvals')

    if not is_executive_leave_applicant(request.user):
        messages.info(request, "Please use the standard departmental leave application form.")
        return redirect('leave_apply')

    if request.method == 'POST':
        form = ExecutiveLeaveApplicationForm(request.POST)
        if form.is_valid():
            leave_req = form.save(commit=False)
            leave_req.user = request.user
            leave_req.status = LeaveRequest.Status.PENDING_SUPERADMIN_APPROVAL
            leave_req.save()

            messages.success(
                request,
                f"Executive leave application for {leave_req.get_leave_type_display()} ({leave_req.start_date} to {leave_req.end_date}) submitted successfully! "
                f"Your request has been routed directly to the Super Admin for review & approval."
            )
            return redirect('my_leaves')
    else:
        form = ExecutiveLeaveApplicationForm()

    return render(request, 'attendance/executive_leave_apply.html', {'form': form})


@login_required
def my_leaves_view(request):
    """View personal leave requests with complete timeline status."""
    leaves = LeaveRequest.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'attendance/my_leaves.html', {'leaves': leaves})


@login_required
def cancel_leave_view(request, leave_id):
    """Allows applicant to cancel a pending leave request."""
    leave_req = get_object_or_404(LeaveRequest, id=leave_id, user=request.user)
    if leave_req.status in [
        LeaveRequest.Status.PENDING_DEPT_REVIEW,
        LeaveRequest.Status.PENDING_MANAGER_APPROVAL,
        LeaveRequest.Status.PENDING_SUPERADMIN_APPROVAL,
    ]:
        leave_req.status = LeaveRequest.Status.CANCELLED
        leave_req.save()
        messages.success(request, "Leave request has been cancelled.")
    else:
        messages.error(request, "Only pending leave applications can be cancelled.")
    return redirect('my_leaves')


# =====================================================================
# 4. Multi-Stage Leave Approvals (Stage 1: Dept Manager, Stage 2: Manager)
# =====================================================================

@login_required
def dept_manager_leave_reviews_view(request):
    """
    Stage 1 Queue: Department Managers review leave applications from staff/executives in their department.
    """
    user = request.user
    if user.role != User.Role.DEPT_MANAGER and get_user_level(user) > 2:
        messages.error(request, "Access restricted to Department Managers and Management.")
        return redirect('attendance_hub')

    if user.role == User.Role.DEPT_MANAGER:
        if not user.department:
            messages.warning(request, "You must be assigned to a department to review staff leaves.")
            return redirect('attendance_hub')
        pending_leaves = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.PENDING_DEPT_REVIEW,
            user__department=user.department
        ).select_related('user', 'user__department')
        department = user.department
    else:
        # Managers / HR can see all pending dept reviews
        pending_leaves = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.PENDING_DEPT_REVIEW
        ).select_related('user', 'user__department')
        department = None

    return render(request, 'attendance/dept_review_list.html', {
        'pending_leaves': pending_leaves,
        'department': department,
    })


@login_required
def dept_manager_review_action_view(request, leave_id):
    """
    Department Manager reviews and recommends/rejects an application:
    - If recommended: advances to PENDING_MANAGER_APPROVAL.
    - If rejected: marked as REJECTED with notes.
    """
    leave_req = get_object_or_404(LeaveRequest, id=leave_id)
    if not can_review_leave_dept_level(request.user, leave_req):
        raise PermissionDenied("You do not have permission to review leaves for this department.")

    if request.method == 'POST':
        form = DeptManagerReviewForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data['notes']

            leave_req.reviewed_by_dept_manager = request.user
            leave_req.dept_manager_notes = notes
            leave_req.dept_manager_reviewed_at = timezone.now()

            if action == 'RECOMMEND':
                leave_req.status = LeaveRequest.Status.PENDING_MANAGER_APPROVAL
                messages.success(
                    request,
                    f"Leave application for {leave_req.user.get_full_name() or leave_req.user.username} has been reviewed and forwarded to the General Manager for final approval."
                )
            else:
                leave_req.status = LeaveRequest.Status.REJECTED
                messages.warning(
                    request,
                    f"Leave application for {leave_req.user.get_full_name() or leave_req.user.username} has been declined at the department review stage."
                )

            leave_req.save()
            return redirect('dept_manager_leave_reviews')
    else:
        form = DeptManagerReviewForm()

    return render(request, 'attendance/dept_review_modal.html', {
        'leave_req': leave_req,
        'form': form
    })


@login_required
def manager_leave_approvals_view(request):
    """
    Stage 2 Queue: Managers & HR give FINAL decision on pending leave applications.
    """
    if get_user_level(request.user) > 2:
        messages.error(request, "Access restricted to Managers and HR (Level 2 & Level 1).")
        return redirect('attendance_hub')

    pending_leaves = LeaveRequest.objects.filter(
        status=LeaveRequest.Status.PENDING_MANAGER_APPROVAL
    ).select_related('user', 'user__department', 'reviewed_by_dept_manager')

    return render(request, 'attendance/manager_approval_list.html', {
        'pending_leaves': pending_leaves
    })


@login_required
def manager_decision_action_view(request, leave_id):
    """
    Manager grants final APPROVAL or REJECTION with remarks.
    When APPROVED, automatically creates/updates daily Attendance records as ON_LEAVE.
    """
    if not can_approve_leave_final(request.user, None):
        raise PermissionDenied("Final leave approval requires Manager authority.")

    leave_req = get_object_or_404(LeaveRequest, id=leave_id)

    if request.method == 'POST':
        form = ManagerFinalDecisionForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data['notes']

            leave_req.approved_by_manager = request.user
            leave_req.manager_decision_notes = notes
            leave_req.manager_decided_at = timezone.now()

            if action == 'APPROVE':
                leave_req.status = LeaveRequest.Status.APPROVED
                leave_req.save()

                # Automatically update Attendance records to ON_LEAVE for the approved date range
                curr = leave_req.start_date
                while curr <= leave_req.end_date:
                    att, _ = Attendance.objects.get_or_create(
                        user=leave_req.user,
                        date=curr
                    )
                    att.status = Attendance.Status.ON_LEAVE
                    att.check_in_notes = f"Approved Leave ({leave_req.get_leave_type_display()})"
                    att.save()
                    curr += timedelta(days=1)

                messages.success(
                    request,
                    f"Leave application for {leave_req.user.get_full_name() or leave_req.user.username} is officially APPROVED! "
                    f"Attendance records updated."
                )
            else:
                leave_req.status = LeaveRequest.Status.REJECTED
                leave_req.save()
                messages.warning(
                    request,
                    f"Leave application for {leave_req.user.get_full_name() or leave_req.user.username} has been REJECTED."
                )

            return redirect('manager_leave_approvals')
    else:
        form = ManagerFinalDecisionForm()

    return render(request, 'attendance/manager_decision_modal.html', {
        'leave_req': leave_req,
        'form': form
    })


# =====================================================================
# 4B. Super Admin Executive Leave Approvals (Server Admin, HR, Manager)
# =====================================================================

@login_required
def superadmin_leave_approvals_view(request):
    """
    Super Admin Executive Review Portal:
    Super Admin has exclusive authority to review, approve, or reject leave applications
    submitted by Server Admin, HR, Manager, and Department Manager personnel.
    """
    if not can_approve_executive_leave(request.user):
        messages.error(request, "Access Denied: Executive Leave Approvals is strictly restricted to the Super Admin.")
        return redirect('attendance_hub')

    pending_leaves = LeaveRequest.objects.filter(
        status=LeaveRequest.Status.PENDING_SUPERADMIN_APPROVAL
    ).select_related('user', 'user__department').order_by('-created_at')

    approved_leaves = LeaveRequest.objects.filter(
        approved_by_superadmin__isnull=False,
        status=LeaveRequest.Status.APPROVED
    ).select_related('user', 'user__department', 'approved_by_superadmin').order_by('-superadmin_decided_at')[:30]

    rejected_leaves = LeaveRequest.objects.filter(
        approved_by_superadmin__isnull=False,
        status=LeaveRequest.Status.REJECTED
    ).select_related('user', 'user__department', 'approved_by_superadmin').order_by('-superadmin_decided_at')[:30]

    context = {
        'pending_leaves': pending_leaves,
        'approved_leaves': approved_leaves,
        'rejected_leaves': rejected_leaves,
        'pending_count': pending_leaves.count(),
        'approved_count': approved_leaves.count(),
        'rejected_count': rejected_leaves.count(),
    }
    return render(request, 'attendance/superadmin_approval_list.html', context)


@login_required
def superadmin_decision_action_view(request, leave_id):
    """
    Super Admin executes final APPROVAL or REJECTION on an Executive Leave Application.
    When APPROVED, automatically creates/updates daily Attendance records as ON_LEAVE.
    """
    if not can_approve_executive_leave(request.user):
        raise PermissionDenied("Only the Super Admin is authorized to decide on executive leave applications.")

    leave_req = get_object_or_404(LeaveRequest, id=leave_id)

    if request.method == 'POST':
        form = SuperadminLeaveDecisionForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data['notes']

            leave_req.approved_by_superadmin = request.user
            leave_req.superadmin_decision_notes = notes
            leave_req.superadmin_decided_at = timezone.now()

            if action == 'APPROVE':
                leave_req.status = LeaveRequest.Status.APPROVED
                leave_req.save()

                # Automatically update Attendance records to ON_LEAVE for the approved date range
                curr = leave_req.start_date
                while curr <= leave_req.end_date:
                    att, _ = Attendance.objects.get_or_create(
                        user=leave_req.user,
                        date=curr
                    )
                    att.status = Attendance.Status.ON_LEAVE
                    att.check_in_notes = f"Approved Executive Leave ({leave_req.get_leave_type_display()}) by Super Admin"
                    att.save()
                    curr += timedelta(days=1)

                messages.success(
                    request,
                    f"Executive leave application for {leave_req.user.get_full_name() or leave_req.user.username} "
                    f"({leave_req.user.get_role_display()}) is officially APPROVED! Attendance roster updated."
                )
            else:
                leave_req.status = LeaveRequest.Status.REJECTED
                leave_req.save()
                messages.warning(
                    request,
                    f"Executive leave application for {leave_req.user.get_full_name() or leave_req.user.username} has been REJECTED."
                )

            return redirect('superadmin_leave_approvals')
    else:
        form = SuperadminLeaveDecisionForm()

    return render(request, 'attendance/superadmin_decision_modal.html', {
        'leave_req': leave_req,
        'form': form
    })


# =====================================================================
# 5. Monthly Attendance Reports & Exports (Restricted to HR & Above)
# =====================================================================

@login_required
def monthly_reports_view(request):
    """
    Monthly attendance report matrix.
    Restricted to HR, Managers, Server Admins, Superadmins (Level 2 and above).
    """
    if not can_view_monthly_reports(request.user):
        messages.error(request, "Access Denied: Monthly attendance reports can only be viewed and downloaded by HR and Management (Level 2+).")
        return redirect('attendance_hub')

    today = date.today()
    form = MonthlyReportFilterForm(request.GET or None)

    if form.is_valid():
        month = int(form.cleaned_data.get('month') or today.month)
        year = int(form.cleaned_data.get('year') or today.year)
        department = form.cleaned_data.get('department')
        selected_user = form.cleaned_data.get('user')
    else:
        month = today.month
        year = today.year
        department = None
        selected_user = None

    users = User.objects.exclude(role=User.Role.SUPERADMIN)
    if department:
        users = users.filter(department=department)
    if selected_user:
        users = users.filter(id=selected_user.id)

    num_days = calendar.monthrange(year, month)[1]
    days_range = range(1, num_days + 1)

    # Fetch attendance matrix
    attendances = Attendance.objects.filter(
        user__in=users,
        date__year=year,
        date__month=month
    )
    att_map = {(a.user_id, a.date.day): a for a in attendances}

    report_rows = []
    for u in users:
        daily_cells = []
        p_cnt = 0
        l_cnt = 0
        hd_cnt = 0
        lv_cnt = 0
        ab_cnt = 0
        tot_mins = 0

        for d in days_range:
            att = att_map.get((u.id, d))
            if att:
                tot_mins += att.work_duration_minutes
                if att.status in [Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.HALF_DAY] or att.is_present:
                    p_cnt += 1
                if att.status == Attendance.Status.LATE or att.is_late:
                    l_cnt += 1
                elif att.status == Attendance.Status.HALF_DAY:
                    hd_cnt += 1
                elif att.status == Attendance.Status.ON_LEAVE:
                    lv_cnt += 1
                elif att.status == Attendance.Status.ABSENT:
                    ab_cnt += 1
            else:
                day_of_week = calendar.weekday(year, month, d)
                if day_of_week in [5, 6]:
                    att = None  # weekend
                else:
                    ab_cnt += 1

            daily_cells.append({
                'day': d,
                'record': att,
            })

        report_rows.append({
            'user': u,
            'daily_cells': daily_cells,
            'present_cnt': p_cnt,
            'late_cnt': l_cnt,
            'half_day_cnt': hd_cnt,
            'leave_cnt': lv_cnt,
            'absent_cnt': ab_cnt,
            'total_hours': round(tot_mins / 60, 1),
        })

    context = {
        'form': form,
        'month': month,
        'year': year,
        'month_name': calendar.month_name[month],
        'department': department,
        'days_range': days_range,
        'report_rows': report_rows,
        'total_employees': users.count(),
    }
    return render(request, 'attendance/monthly_report.html', context)


@login_required
def export_monthly_excel_view(request):
    """Exports monthly attendance matrix to Excel (.xlsx). Restricted to Level 2+."""
    if not can_view_monthly_reports(request.user):
        messages.error(request, "Access Denied: Monthly attendance export is restricted to HR and Management.")
        return redirect('attendance_hub')

    today = date.today()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    dept_id = request.GET.get('department')
    department = Department.objects.filter(id=dept_id).first() if dept_id else None

    users = User.objects.exclude(role=User.Role.SUPERADMIN)
    if department:
        users = users.filter(department=department)

    user_id = request.GET.get('user')
    if user_id:
        users = users.filter(id=user_id)

    excel_buffer = generate_monthly_attendance_excel(users, year, month, department)
    filename = f"Aider_Attendance_{calendar.month_name[month]}_{year}.xlsx"

    response = HttpResponse(
        excel_buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_monthly_pdf_view(request):
    """Exports monthly attendance report to PDF. Restricted to Level 2+."""
    if not can_view_monthly_reports(request.user):
        messages.error(request, "Access Denied: Monthly attendance export is restricted to HR and Management.")
        return redirect('attendance_hub')

    today = date.today()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    dept_id = request.GET.get('department')
    department = Department.objects.filter(id=dept_id).first() if dept_id else None

    users = User.objects.exclude(role=User.Role.SUPERADMIN)
    if department:
        users = users.filter(department=department)

    user_id = request.GET.get('user')
    if user_id:
        users = users.filter(id=user_id)

    pdf_buffer = generate_monthly_attendance_pdf(users, year, month, department)
    filename = f"Aider_Attendance_{calendar.month_name[month]}_{year}.pdf"

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
