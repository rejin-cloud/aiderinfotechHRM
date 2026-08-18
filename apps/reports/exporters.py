import io
from datetime import datetime
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.pdfgen import canvas

from apps.users.models import User
from apps.departments.models import Department, Branch


# ==========================================
# EXCEL EXPORT ENGINE (openpyxl + pandas)
# ==========================================

def generate_multi_dept_excel(department_id=None):
    """
    Generates a multi-sheet Excel workbook with styling, summary KPIs,
    master directory, and individual department breakdown sheets.
    """
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='1E293B', end_color='1E293B', fill_type='solid')
    title_font = Font(name='Segoe UI', size=16, bold=True, color='0F172A')
    subtitle_font = Font(name='Segoe UI', size=10, italic=True, color='64748B')
    bold_font = Font(name='Segoe UI', size=10, bold=True)
    normal_font = Font(name='Segoe UI', size=10)
    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    # -------------------------------------------------------------
    # Sheet 1: Executive Summary
    # -------------------------------------------------------------
    ws_summary = wb.create_sheet(title='Executive Summary')
    ws_summary.views.sheetView[0].showGridLines = True

    ws_summary['A1'] = "Aider Infotech Enterprise Operations"
    ws_summary['A1'].font = title_font
    ws_summary['A2'] = f"Organizational Roster & Technology Audit Report | Exported on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    ws_summary['A2'].font = subtitle_font

    ws_summary['A4'] = "System Metric"
    ws_summary['B4'] = "Count / Value"
    ws_summary['A4'].font = header_font
    ws_summary['B4'].font = header_font
    ws_summary['A4'].fill = header_fill
    ws_summary['B4'].fill = header_fill

    total_users = User.objects.count()
    total_depts = Department.objects.count()
    total_branches = Branch.objects.count()

    metrics = [
        ("Total Active Personnel", total_users),
        ("Total Departments", total_depts),
        ("Total Active Branches", total_branches),
    ]

    for idx, (metric, val) in enumerate(metrics, start=5):
        ws_summary[f'A{idx}'] = metric
        ws_summary[f'B{idx}'] = val
        ws_summary[f'A{idx}'].font = normal_font
        ws_summary[f'B{idx}'].font = bold_font
        ws_summary[f'A{idx}'].border = thin_border
        ws_summary[f'B{idx}'].border = thin_border

    # Department Breakdown Table on Summary Sheet
    row_cursor = 10
    ws_summary[f'A{row_cursor}'] = "Department Name"
    ws_summary[f'B{row_cursor}'] = "Branches Count"
    ws_summary[f'C{row_cursor}'] = "Assigned Members"
    for col in ['A', 'B', 'C']:
        ws_summary[f'{col}{row_cursor}'].font = header_font
        ws_summary[f'{col}{row_cursor}'].fill = PatternFill(start_color='334155', end_color='334155', fill_type='solid')

    row_cursor += 1
    departments = Department.objects.all()
    for dept in departments:
        ws_summary[f'A{row_cursor}'] = dept.name
        ws_summary[f'B{row_cursor}'] = dept.branches.count()
        ws_summary[f'C{row_cursor}'] = dept.users.count()
        for col in ['A', 'B', 'C']:
            ws_summary[f'{col}{row_cursor}'].font = normal_font
            ws_summary[f'{col}{row_cursor}'].border = thin_border
        row_cursor += 1

    # -------------------------------------------------------------
    # Sheet 2: Master Employee Directory
    # -------------------------------------------------------------
    ws_master = wb.create_sheet(title='Master Directory')
    ws_master.views.sheetView[0].showGridLines = True

    master_headers = [
        "Employee ID", "Full Name", "Username", "Email", "Role",
        "System Level", "Department", "Branch", "Designation", "Phone", "Joining Date"
    ]

    for col_idx, h_text in enumerate(master_headers, start=1):
        cell = ws_master.cell(row=1, column=col_idx, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')

    users_qs = User.objects.select_related('department', 'branch').all()
    if department_id:
        users_qs = users_qs.filter(department_id=department_id)

    for row_idx, u in enumerate(users_qs, start=2):
        row_data = [
            u.employee_id or f"EMP-{u.id:04d}",
            u.get_full_name() or u.username,
            u.username,
            u.email or 'N/A',
            u.get_role_display(),
            f"Level {u.level}",
            u.department.name if u.department else 'Unassigned',
            u.branch.name if u.branch else 'Core / None',
            u.designation or 'Staff',
            u.phone or 'N/A',
            u.joining_date.strftime('%Y-%m-%d') if u.joining_date else 'N/A'
        ]
        for col_idx, val in enumerate(row_data, start=1):
            cell = ws_master.cell(row=row_idx, column=col_idx, value=val)
            cell.font = normal_font
            cell.border = thin_border
            if col_idx in [1, 5, 6, 11]:
                cell.alignment = Alignment(horizontal='center')

    # -------------------------------------------------------------
    # Per-Department Sheets
    # -------------------------------------------------------------
    for dept in departments:
        # Excel sheet names max 31 chars
        sheet_title = dept.name[:28].replace('/', '-').replace('\\', '-')
        ws_dept = wb.create_sheet(title=sheet_title)
        ws_dept.views.sheetView[0].showGridLines = True

        ws_dept['A1'] = f"Department: {dept.name}"
        ws_dept['A1'].font = title_font
        ws_dept['A2'] = f"Description: {dept.description or 'Standard organizational unit'}"
        ws_dept['A2'].font = subtitle_font

        dept_headers = ["Emp ID", "Name", "Role", "Branch", "Designation", "Email", "Phone"]
        for col_idx, h_text in enumerate(dept_headers, start=1):
            cell = ws_dept.cell(row=4, column=col_idx, value=h_text)
            cell.font = header_font
            cell.fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')

        dept_users = dept.users.select_related('branch').all()
        if not dept_users.exists():
            ws_dept['A5'] = "No personnel assigned to this department yet."
            ws_dept['A5'].font = subtitle_font
        else:
            for row_idx, u in enumerate(dept_users, start=5):
                r_vals = [
                    u.employee_id or f"EMP-{u.id:04d}",
                    u.get_full_name() or u.username,
                    u.get_role_display(),
                    u.branch.name if u.branch else 'Core Department',
                    u.designation or 'Staff',
                    u.email or 'N/A',
                    u.phone or 'N/A'
                ]
                for col_idx, val in enumerate(r_vals, start=1):
                    cell = ws_dept.cell(row=row_idx, column=col_idx, value=val)
                    cell.font = normal_font
                    cell.border = thin_border

    # Auto-adjust column widths on all sheets
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if '\n' in val_str:
                    val_str = val_str.split('\n')[0]
                max_len = max(max_len, len(val_str))
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ==========================================
# PDF EXPORT ENGINE (ReportLab)
# ==========================================

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header rule & text
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(40, 792 - 40, 612 - 40, 792 - 40)
        self.drawString(40, 792 - 35, "HRMS V1 | Official Enterprise Organizational Documentation")
        
        # Footer rule & text
        self.line(40, 45, 612 - 40, 45)
        self.drawString(40, 32, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | Confidential HR Record")
        self.drawRightString(612 - 40, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def generate_hr_pdf_report(department_id=None):
    """
    Generates a PDF document containing complete HR organization details,
    departments, branches, role distribution, and employee rosters.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=50,
        bottomMargin=55
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor('#475569'),
        spaceAfter=12
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=14,
        spaceAfter=6
    )

    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1E293B')
    )

    cell_header = ParagraphStyle(
        'TableCellHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )

    story = []

    # Title Block
    story.append(Paragraph("Aider Infotech", title_style))
    story.append(Paragraph("Comprehensive Organizational Hierarchy & Personnel Distribution Report", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563EB'), spaceAfter=14))

    # Executive Overview
    story.append(Paragraph("1. Executive Summary & KPIs", h2_style))
    
    total_users = User.objects.count()
    total_depts = Department.objects.count()
    total_branches = Branch.objects.count()
    
    kpi_data = [
        [Paragraph("<b>Metric</b>", cell_header), Paragraph("<b>Count / Status</b>", cell_header), Paragraph("<b>Description</b>", cell_header)],
        [Paragraph("Total Employees", cell_style), Paragraph(f"<b>{total_users}</b>", cell_style), Paragraph("Total active accounts across all tiers", cell_style)],
        [Paragraph("Departments", cell_style), Paragraph(f"<b>{total_depts}</b>", cell_style), Paragraph("Provisioned organizational divisions", cell_style)],
        [Paragraph("Branches / Units", cell_style), Paragraph(f"<b>{total_branches}</b>", cell_style), Paragraph("Active operational sub-branches", cell_style)],
    ]

    t_kpi = Table(kpi_data, colWidths=[130, 90, 312])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F8FAFC'), colors.white]),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 12))

    # Department & Branch Breakdown Table
    story.append(Paragraph("2. Departmental & Branch Topology", h2_style))
    dept_table_data = [
        [Paragraph("<b>Department Name</b>", cell_header), Paragraph("<b>Branches</b>", cell_header), Paragraph("<b>Headcount</b>", cell_header)]
    ]
    
    depts = Department.objects.prefetch_related('branches', 'users').all()
    for d in depts:
        branch_names = ", ".join([b.name for b in d.branches.all()]) or "None (Core level)"
        dept_table_data.append([
            Paragraph(f"<b>{d.name}</b>", cell_style),
            Paragraph(branch_names, cell_style),
            Paragraph(str(d.users.count()), cell_style)
        ])

    t_dept = Table(dept_table_data, colWidths=[150, 310, 72])
    t_dept.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F8FAFC'), colors.white]),
    ]))
    story.append(t_dept)
    story.append(Spacer(1, 14))

    # Master Employee Roster Table
    story.append(Paragraph("3. Personnel Directory & RBAC Tiers", h2_style))
    users_qs = User.objects.select_related('department', 'branch').order_by('id')
    if department_id:
        users_qs = users_qs.filter(department_id=department_id)

    roster_data = [
        [
            Paragraph("<b>Emp ID</b>", cell_header),
            Paragraph("<b>Name</b>", cell_header),
            Paragraph("<b>Role</b>", cell_header),
            Paragraph("<b>Department</b>", cell_header),
            Paragraph("<b>Branch</b>", cell_header),
            Paragraph("<b>Email</b>", cell_header),
        ]
    ]

    for u in users_qs:
        roster_data.append([
            Paragraph(u.employee_id or f"EMP-{u.id:04d}", cell_style),
            Paragraph(u.get_full_name() or u.username, cell_style),
            Paragraph(u.get_role_display(), cell_style),
            Paragraph(u.department.name if u.department else '—', cell_style),
            Paragraph(u.branch.name if u.branch else '—', cell_style),
            Paragraph(u.email or '—', cell_style),
        ])

    t_roster = Table(roster_data, colWidths=[65, 105, 95, 95, 85, 87])
    t_roster.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F8FAFC'), colors.white]),
    ]))
    story.append(t_roster)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


def generate_employee_dossier_pdf(user):
    """
    Generates an official single-person employee profile dossier & ID sheet.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=45,
        rightMargin=45,
        topMargin=50,
        bottomMargin=55
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DossierTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0F172A')
    )
    subtitle_style = ParagraphStyle(
        'DossierSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#64748B')
    )
    cell_lbl = ParagraphStyle('DossierLbl', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#475569'))
    cell_val = ParagraphStyle('DossierVal', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#0F172A'))

    story = [
        Paragraph("Aider Infotech | Official Personnel Dossier", title_style),
        Paragraph(f"Confidential Human Resources Record for {user.get_full_name() or user.username}", subtitle_style),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563EB'), spaceAfter=14),
    ]

    details = [
        [Paragraph("Full Legal Name", cell_lbl), Paragraph(user.get_full_name() or user.username, cell_val)],
        [Paragraph("Employee ID", cell_lbl), Paragraph(user.employee_id or f"EMP-{user.id:04d}", cell_val)],
        [Paragraph("Assigned Role", cell_lbl), Paragraph(f"<b>{user.get_role_display()}</b> (Level {user.level})", cell_val)],
        [Paragraph("Department", cell_lbl), Paragraph(user.department.name if user.department else "Unassigned", cell_val)],
        [Paragraph("Branch / Station", cell_lbl), Paragraph(user.branch.name if user.branch else "Core Division / Headquarters", cell_val)],
        [Paragraph("Official Email", cell_lbl), Paragraph(user.email or "N/A", cell_val)],
        [Paragraph("Phone Number", cell_lbl), Paragraph(user.phone or "N/A", cell_val)],
        [Paragraph("Designation", cell_lbl), Paragraph(user.designation or "Staff Member", cell_val)],
        [Paragraph("Date of Joining", cell_lbl), Paragraph(user.joining_date.strftime('%B %d, %Y') if user.joining_date else "N/A", cell_val)],
        [Paragraph("Account Status", cell_lbl), Paragraph("Active & In Good Standing" if user.is_active else "Inactive", cell_val)],
    ]

    t_details = Table(details, colWidths=[160, 362])
    t_details.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_details)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer
