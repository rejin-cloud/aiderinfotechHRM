from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from datetime import datetime
from apps.users.models import User
from apps.departments.models import Department
from apps.reports.exporters import (
    generate_multi_dept_excel,
    generate_hr_pdf_report,
    generate_employee_dossier_pdf
)

@login_required
def reports_hub_view(request):
    departments = Department.objects.all()
    return render(request, 'reports/reports_hub.html', {
        'departments': departments,
        'page_title': 'HRMS Reports & Document Generation Engine'
    })

@login_required
def export_excel_view(request):
    dept_id = request.GET.get('department_id')
    buffer = generate_multi_dept_excel(department_id=dept_id)
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"HRMS_Organization_Export_{timestamp}.xlsx"
    
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def export_pdf_view(request):
    dept_id = request.GET.get('department_id')
    buffer = generate_hr_pdf_report(department_id=dept_id)
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"HRMS_Organization_Report_{timestamp}.pdf"
    
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/pdf'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def export_dossier_pdf_view(request, user_id=None):
    if user_id:
        target_user = get_object_or_404(User, pk=user_id)
    else:
        target_user = request.user

    buffer = generate_employee_dossier_pdf(target_user)
    filename = f"Dossier_{target_user.username}.pdf"
    
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/pdf'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
