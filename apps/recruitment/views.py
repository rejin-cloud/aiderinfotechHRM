from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from .models import Candidate
from .forms import (
    CandidateForm,
    CandidateCallLogForm,
    CandidateDecisionForm,
    InterviewScheduleForm,
    CandidateInterviewOutcomeForm,
)
from apps.departments.models import Department, Branch


def hr_or_management_required(view_func):
    """
    Ensures user is HR, Manager, Department Manager, Superadmin, or Server Admin.
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        user = request.user
        allowed_roles = [
            user.Role.HR,
            user.Role.MANAGER,
            user.Role.DEPT_MANAGER,
            user.Role.SUPERADMIN,
            user.Role.SERVER_ADMIN,
        ]
        if user.role not in allowed_roles:
            messages.error(request, "You do not have administrative authority to access recruitment records.")
            return redirect('dashboard_router')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@hr_or_management_required
def candidate_list_view(request):
    """
    Recruitment Pipeline & Candidate Directory with status tabs, stage counters,
    and 1-click workflow actions.
    """
    status_filter = request.GET.get('status', 'ALL').strip().upper()
    dept_filter = request.GET.get('department', '').strip()
    search_q = request.GET.get('q', '').strip()

    qs = Candidate.objects.select_related('department', 'branch', 'called_by', 'reviewed_by').all()

    # Apply Search
    if search_q:
        qs = qs.filter(
            Q(name__icontains=search_q) |
            Q(phone__icontains=search_q) |
            Q(place__icontains=search_q) |
            Q(designation_applied__icontains=search_q) |
            Q(email__icontains=search_q)
        )

    # Apply Department Filter
    if dept_filter:
        qs = qs.filter(department_id=dept_filter)

    # Stage Counts
    base_qs = Candidate.objects.all()
    if dept_filter:
        base_qs = base_qs.filter(department_id=dept_filter)

    to_be_called_cnt = base_qs.filter(status=Candidate.Status.TO_BE_CALLED).count()
    called_cnt = base_qs.filter(status=Candidate.Status.CALLED).count()
    approved_cnt = base_qs.filter(status=Candidate.Status.APPROVED).count()
    interview_cnt = base_qs.filter(status=Candidate.Status.INTERVIEW_SCHEDULED).count()
    rejected_cnt = base_qs.filter(status=Candidate.Status.REJECTED).count()
    total_cnt = base_qs.count()

    # Apply Status Tab Filter
    if status_filter in Candidate.Status.values:
        qs = qs.filter(status=status_filter)

    departments = Department.objects.all()

    return render(request, 'recruitment/candidate_list.html', {
        'candidates': qs,
        'current_status': status_filter,
        'to_be_called_cnt': to_be_called_cnt,
        'called_cnt': called_cnt,
        'approved_cnt': approved_cnt,
        'interview_cnt': interview_cnt,
        'rejected_cnt': rejected_cnt,
        'total_cnt': total_cnt,
        'departments': departments,
        'selected_dept': dept_filter,
        'search_q': search_q,
        'page_title': 'Recruitment & Candidate Pipeline',
    })


@login_required
@hr_or_management_required
def candidate_approved_list_view(request):
    """
    Dedicated Page for Approved Candidates (Shortlisted after telephonic screening).
    Displays complete summary: Name, Phone, Place, Department, Branch, Role Applied,
    and direct triggers to arrange interviews or view full dossier.
    """
    dept_filter = request.GET.get('department', '').strip()
    search_q = request.GET.get('q', '').strip()

    qs = Candidate.objects.filter(
        status__in=[Candidate.Status.APPROVED, Candidate.Status.INTERVIEW_SCHEDULED, Candidate.Status.SELECTED]
    ).select_related('department', 'branch', 'called_by', 'reviewed_by')

    if search_q:
        qs = qs.filter(
            Q(name__icontains=search_q) |
            Q(phone__icontains=search_q) |
            Q(place__icontains=search_q) |
            Q(designation_applied__icontains=search_q)
        )

    if dept_filter:
        qs = qs.filter(department_id=dept_filter)

    approved_only_cnt = Candidate.objects.filter(status=Candidate.Status.APPROVED).count()
    interview_scheduled_cnt = Candidate.objects.filter(status=Candidate.Status.INTERVIEW_SCHEDULED).count()
    selected_cnt = Candidate.objects.filter(status=Candidate.Status.SELECTED).count()
    departments = Department.objects.all()

    return render(request, 'recruitment/candidate_approved_list.html', {
        'candidates': qs,
        'approved_only_cnt': approved_only_cnt,
        'interview_scheduled_cnt': interview_scheduled_cnt,
        'selected_cnt': selected_cnt,
        'total_approved_cnt': qs.count(),
        'departments': departments,
        'selected_dept': dept_filter,
        'search_q': search_q,
        'page_title': 'Approved Candidates Roster',
    })


@login_required
@hr_or_management_required
def candidate_detail_view(request, candidate_id):
    """
    Full Candidate Dossier showing all application details, calling summary,
    decision notes, interview arrangement details, and administrative controls.
    """
    candidate = get_object_or_404(
        Candidate.objects.select_related('department', 'branch', 'called_by', 'reviewed_by', 'created_by'),
        id=candidate_id
    )

    call_form = CandidateCallLogForm()
    decision_form = CandidateDecisionForm()
    interview_form = InterviewScheduleForm(instance=candidate)

    return render(request, 'recruitment/candidate_detail.html', {
        'candidate': candidate,
        'call_form': call_form,
        'decision_form': decision_form,
        'interview_form': interview_form,
        'page_title': f"Candidate Dossier: {candidate.name}",
    })


@login_required
@hr_or_management_required
def candidate_create_view(request):
    """
    Registers a new candidate applicant into the pipeline (defaults to 'To Be Called').
    """
    if request.method == 'POST':
        form = CandidateForm(request.POST, request.FILES)
        if form.is_valid():
            candidate = form.save(commit=False)
            candidate.created_by = request.user
            candidate.status = Candidate.Status.TO_BE_CALLED
            candidate.save()
            messages.success(request, f"Candidate '{candidate.name}' registered successfully and added to 'To Be Called' list.")
            return redirect('candidate_detail', candidate_id=candidate.id)
    else:
        form = CandidateForm()

    return render(request, 'recruitment/candidate_create.html', {
        'form': form,
        'page_title': 'Register New Candidate Application',
    })


@login_required
@hr_or_management_required
def candidate_edit_view(request, candidate_id):
    """
    Edits an existing candidate's personal or applying department details.
    """
    candidate = get_object_or_404(Candidate, id=candidate_id)
    if request.method == 'POST':
        form = CandidateForm(request.POST, request.FILES, instance=candidate)
        if form.is_valid():
            form.save()
            messages.success(request, f"Candidate profile for '{candidate.name}' updated successfully.")
            return redirect('candidate_detail', candidate_id=candidate.id)
    else:
        form = CandidateForm(instance=candidate)

    return render(request, 'recruitment/candidate_edit.html', {
        'form': form,
        'candidate': candidate,
        'page_title': f"Edit Candidate: {candidate.name}",
    })


@login_required
@hr_or_management_required
def candidate_mark_called_view(request, candidate_id):
    """
    Logs the telephonic screening call: records call discussion notes, rating,
    caller HR officer, timestamp, and transitions candidate status.
    """
    candidate = get_object_or_404(Candidate, id=candidate_id)

    if request.method == 'POST':
        form = CandidateCallLogForm(request.POST)
        if form.is_valid():
            outcome = form.cleaned_data['call_outcome']
            call_notes = form.cleaned_data['call_notes']
            rating = form.cleaned_data.get('call_rating') or None

            candidate.called_at = timezone.now()
            candidate.called_by = request.user
            candidate.call_notes = call_notes
            if rating:
                candidate.call_rating = int(rating)

            if outcome == 'APPROVED':
                candidate.status = Candidate.Status.APPROVED
                candidate.reviewed_at = timezone.now()
                candidate.reviewed_by = request.user
                candidate.approval_notes = f"Approved & shortlisted during phone call by {request.user.get_full_name() or request.user.username}."
                messages.success(request, f"Call logged & candidate '{candidate.name}' marked as Approved (Shortlisted).")
            elif outcome == 'REJECTED':
                candidate.status = Candidate.Status.REJECTED
                candidate.reviewed_at = timezone.now()
                candidate.reviewed_by = request.user
                candidate.approval_notes = f"Rejected following phone discussion by {request.user.get_full_name() or request.user.username}."
                messages.warning(request, f"Call logged & candidate '{candidate.name}' marked as Rejected.")
            else:
                candidate.status = Candidate.Status.CALLED
                messages.info(request, f"Call logged for candidate '{candidate.name}'. Status set to 'Called'. Ready for decision.")

            candidate.save()
            return redirect('candidate_detail', candidate_id=candidate.id)
    else:
        form = CandidateCallLogForm(initial={'call_notes': candidate.call_notes, 'call_rating': candidate.call_rating})

    return render(request, 'recruitment/candidate_mark_called.html', {
        'candidate': candidate,
        'form': form,
        'page_title': f"Log Phone Screening: {candidate.name}",
    })


@login_required
@hr_or_management_required
def candidate_decide_view(request, candidate_id):
    """
    Records HR / Manager screening decision for a called candidate (Approve / Reject).
    """
    candidate = get_object_or_404(Candidate, id=candidate_id)

    if request.method == 'POST':
        form = CandidateDecisionForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            approval_notes = form.cleaned_data.get('approval_notes', '')

            candidate.reviewed_at = timezone.now()
            candidate.reviewed_by = request.user
            candidate.approval_notes = approval_notes

            if decision == 'APPROVED':
                candidate.status = Candidate.Status.APPROVED
                messages.success(request, f"Candidate '{candidate.name}' has been Approved and shortlisted for interview!")
            else:
                candidate.status = Candidate.Status.REJECTED
                messages.warning(request, f"Candidate '{candidate.name}' has been marked as Rejected.")

            candidate.save()
            return redirect('candidate_detail', candidate_id=candidate.id)
    else:
        form = CandidateDecisionForm(initial={'approval_notes': candidate.approval_notes})

    return render(request, 'recruitment/candidate_decide.html', {
        'candidate': candidate,
        'form': form,
        'page_title': f"Screening Decision: {candidate.name}",
    })


@login_required
@hr_or_management_required
def candidate_schedule_interview_view(request, candidate_id):
    """
    Arranges an official interview for an approved candidate with date, time,
    venue / Google Meet link, interviewer panel, and instructions.
    """
    candidate = get_object_or_404(Candidate, id=candidate_id)

    if candidate.status == Candidate.Status.REJECTED:
        messages.error(
            request,
            f"Cannot arrange an interview for '{candidate.name}' because this candidate is marked as Rejected. Re-evaluate and approve the candidate first."
        )
        return redirect('candidate_detail', candidate_id=candidate.id)

    if request.method == 'POST':
        form = InterviewScheduleForm(request.POST, instance=candidate)
        if form.is_valid():
            cand = form.save(commit=False)
            cand.status = Candidate.Status.INTERVIEW_SCHEDULED
            cand.save()
            messages.success(request, f"Interview arranged for '{candidate.name}' on {candidate.interview_date} at {candidate.interview_time}!")
            return redirect('candidate_detail', candidate_id=candidate.id)
    else:
        form = InterviewScheduleForm(instance=candidate)

    return render(request, 'recruitment/candidate_schedule_interview.html', {
        'candidate': candidate,
        'form': form,
        'page_title': f"Arrange Interview: {candidate.name}",
    })


@login_required
@hr_or_management_required
def candidate_interview_outcome_view(request, candidate_id):
    """
    Records post-interview evaluation outcome (Approved / Rejected).
    If Approved (Selected): Prompts HR with the shareable message and instructions
    to invite the candidate to register on our HRMS system.
    If Rejected: Updates candidate status to Rejected with feedback remarks.
    """
    candidate = get_object_or_404(Candidate, id=candidate_id)

    if request.method == 'POST':
        form = CandidateInterviewOutcomeForm(request.POST)
        if form.is_valid():
            outcome = form.cleaned_data['outcome']
            feedback = form.cleaned_data.get('interview_feedback', '')

            candidate.interview_feedback = feedback
            candidate.reviewed_at = timezone.now()
            candidate.reviewed_by = request.user

            if outcome == 'SELECTED':
                candidate.status = Candidate.Status.SELECTED
                candidate.save()
                messages.success(
                    request,
                    f"Candidate '{candidate.name}' has been Approved post-interview! "
                    "Please share the HRMS registration link with the candidate and ask them to register to our HR system."
                )
            else:
                candidate.status = Candidate.Status.REJECTED
                candidate.approval_notes = f"Rejected post-interview: {feedback}"
                candidate.save()
                messages.warning(
                    request,
                    f"Candidate '{candidate.name}' has been marked as Rejected post-interview."
                )

            return redirect('candidate_detail', candidate_id=candidate.id)
    else:
        initial_decision = request.GET.get('decision', 'SELECTED')
        if initial_decision not in ['SELECTED', 'REJECTED']:
            initial_decision = 'SELECTED'
        form = CandidateInterviewOutcomeForm(initial={
            'outcome': initial_decision,
            'interview_feedback': candidate.interview_feedback,
        })

    return render(request, 'recruitment/candidate_interview_outcome.html', {
        'candidate': candidate,
        'form': form,
        'page_title': f"Interview Outcome & Evaluation: {candidate.name}",
    })


@login_required
@hr_or_management_required
def candidate_delete_view(request, candidate_id):
    """
    Deletes candidate application record with confirmation dialog.
    """
    candidate = get_object_or_404(Candidate, id=candidate_id)
    if request.method == 'POST':
        name = candidate.name
        candidate.delete()
        messages.success(request, f"Candidate record '{name}' was permanently deleted.")
        return redirect('candidate_list')

    return render(request, 'recruitment/candidate_confirm_delete.html', {
        'candidate': candidate,
        'page_title': f"Delete Candidate: {candidate.name}",
    })
