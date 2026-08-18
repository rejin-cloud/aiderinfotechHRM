from django.test import TestCase
from apps.users.models import User
from apps.departments.models import Department, Branch
from apps.reports.exporters import generate_multi_dept_excel, generate_hr_pdf_report, generate_employee_dossier_pdf

class DocumentEngineTest(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Aider Creative", description="Marketing and design")
        self.branch = Branch.objects.create(department=self.dept, name="Designing", location="Studio A")
        self.user = User.objects.create_user(
            username="alex_v",
            first_name="Alex",
            last_name="Vance",
            role=User.Role.SUPERADMIN,
            department=self.dept,
            branch=self.branch,
            employee_id="EMP-0001"
        )

    def test_excel_export_generation(self):
        buf = generate_multi_dept_excel()
        self.assertIsNotNone(buf)
        data = buf.getvalue()
        self.assertGreater(len(data), 0)
        # Verify it's a valid zip/xlsx header PK\x03\x04
        self.assertTrue(data.startswith(b'PK\x03\x04'))

    def test_pdf_report_generation(self):
        buf = generate_hr_pdf_report()
        self.assertIsNotNone(buf)
        data = buf.getvalue()
        self.assertGreater(len(data), 0)
        # Verify it's a valid PDF header %PDF
        self.assertTrue(data.startswith(b'%PDF'))

    def test_employee_dossier_pdf_generation(self):
        buf = generate_employee_dossier_pdf(self.user)
        self.assertIsNotNone(buf)
        data = buf.getvalue()
        self.assertGreater(len(data), 0)
        self.assertTrue(data.startswith(b'%PDF'))
