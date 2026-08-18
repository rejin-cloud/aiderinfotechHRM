from datetime import date, datetime, timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import Attendance, LeaveRequest
from apps.departments.models import Branch, Department
from apps.users.models import User


class AttendanceAndLeaveWorkflowTest(TestCase):
    def setUp(self):
        # Create Departments and Branches
        self.dept_engineering = Department.objects.create(name="Engineering")
        self.dept_creative = Department.objects.create(name="Creative")
        self.branch_dev = Branch.objects.create(department=self.dept_engineering, name="Core Dev")

        # Create Users
        self.superadmin = User.objects.create_user(
            username="superadmin",
            password="password123",
            role=User.Role.SUPERADMIN
        )
        self.server_admin = User.objects.create_user(
            username="serveradmin",
            password="password123",
            role=User.Role.SERVER_ADMIN
        )
        self.hr = User.objects.create_user(
            username="hr_user",
            password="password123",
            role=User.Role.HR,
            department=self.dept_engineering
        )
        self.manager = User.objects.create_user(
            username="manager_user",
            password="password123",
            role=User.Role.MANAGER,
            department=self.dept_engineering
        )
        self.dept_mgr_eng = User.objects.create_user(
            username="deptmgr_eng",
            password="password123",
            role=User.Role.DEPT_MANAGER,
            department=self.dept_engineering,
            branch=self.branch_dev
        )
        self.dept_mgr_creative = User.objects.create_user(
            username="deptmgr_creative",
            password="password123",
            role=User.Role.DEPT_MANAGER,
            department=self.dept_creative
        )
        self.staff_eng = User.objects.create_user(
            username="staff_eng",
            password="password123",
            role=User.Role.STAFF,
            department=self.dept_engineering,
            branch=self.branch_dev
        )
        self.staff_creative = User.objects.create_user(
            username="staff_creative",
            password="password123",
            role=User.Role.STAFF,
            department=self.dept_creative
        )

    def test_clock_in_and_clock_out(self):
        # Staff clocks in
        self.client.force_login(self.staff_eng)
        res_in = self.client.post(reverse('attendance_check_in'), {'notes': 'Starting work today'})
        self.assertRedirects(res_in, reverse('attendance_hub'))

        today = timezone.localdate()
        att = Attendance.objects.filter(user=self.staff_eng, date=today).first()
        self.assertIsNotNone(att)
        self.assertIsNotNone(att.check_in)
        self.assertEqual(att.check_in_notes, 'Starting work today')
        self.assertIn(att.status, [Attendance.Status.PRESENT, Attendance.Status.LATE])

        # Staff clocks out
        res_out = self.client.post(reverse('attendance_check_out'), {'notes': 'Finished shift'})
        self.assertRedirects(res_out, reverse('attendance_hub'))

        att.refresh_from_db()
        self.assertIsNotNone(att.check_out)
        self.assertEqual(att.check_out_notes, 'Finished shift')

    def test_work_start_time_cutoff_930am(self):
        # Test 1: Check-in at 09:15 AM IST (Before 09:30 AM) -> Status: PRESENT
        dt_ontime = timezone.datetime(2026, 8, 18, 9, 15, 0, tzinfo=timezone.get_current_timezone())
        att_ontime = Attendance(user=self.staff_eng, date=dt_ontime.date(), check_in=dt_ontime)
        att_ontime.calculate_duration_and_status()
        self.assertEqual(att_ontime.status, Attendance.Status.PRESENT)

        # Test 2: Check-in at exactly 09:30 AM IST -> Status: PRESENT
        dt_exact = timezone.datetime(2026, 8, 18, 9, 30, 0, tzinfo=timezone.get_current_timezone())
        att_exact = Attendance(user=self.staff_eng, date=dt_exact.date(), check_in=dt_exact)
        att_exact.calculate_duration_and_status()
        self.assertEqual(att_exact.status, Attendance.Status.PRESENT)

        # Test 3: Check-in at 09:31 AM IST (After 09:30 AM) -> Status: LATE, is_present: True, is_late: True
        dt_late = timezone.datetime(2026, 8, 18, 9, 31, 0, tzinfo=timezone.get_current_timezone())
        att_late = Attendance(user=self.staff_eng, date=dt_late.date(), check_in=dt_late)
        att_late.calculate_duration_and_status()
        self.assertEqual(att_late.status, Attendance.Status.LATE)
        self.assertTrue(att_late.is_late)
        self.assertTrue(att_late.is_present)

    def test_superadmin_attendance_exemption(self):
        # Superadmin tries to clock in -> redirected with exemption notice
        self.client.force_login(self.superadmin)
        res = self.client.post(reverse('attendance_check_in'), {})
        self.assertRedirects(res, reverse('attendance_hub'))
        # No attendance record created for superadmin
        self.assertEqual(Attendance.objects.filter(user=self.superadmin).count(), 0)

    def test_multi_stage_leave_workflow(self):
        # Step 1: Staff submits leave application
        self.client.force_login(self.staff_eng)
        today = date.today()
        start = today + timedelta(days=2)
        end = today + timedelta(days=4)

        post_data = {
            'leave_type': LeaveRequest.LeaveType.CASUAL,
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d'),
            'reason': 'Family function vacation',
        }
        res_apply = self.client.post(reverse('leave_apply'), post_data)
        self.assertRedirects(res_apply, reverse('my_leaves'))

        leave_req = LeaveRequest.objects.filter(user=self.staff_eng).first()
        self.assertIsNotNone(leave_req)
        # For Level 4 in a department, initial status is PENDING_DEPT_REVIEW
        self.assertEqual(leave_req.status, LeaveRequest.Status.PENDING_DEPT_REVIEW)

        # Step 2: Department Manager reviews and forwards
        self.client.force_login(self.dept_mgr_eng)
        review_data = {
            'action': 'RECOMMEND',
            'notes': 'Tasks covered by team. Recommended to General Manager.'
        }
        res_review = self.client.post(reverse('dept_manager_review_action', kwargs={'leave_id': leave_req.id}), review_data)
        self.assertRedirects(res_review, reverse('dept_manager_leave_reviews'))

        leave_req.refresh_from_db()
        self.assertEqual(leave_req.status, LeaveRequest.Status.PENDING_MANAGER_APPROVAL)
        self.assertEqual(leave_req.reviewed_by_dept_manager, self.dept_mgr_eng)
        self.assertEqual(leave_req.dept_manager_notes, 'Tasks covered by team. Recommended to General Manager.')

        # Step 3: General Manager grants final authorization
        self.client.force_login(self.manager)
        decision_data = {
            'action': 'APPROVE',
            'notes': 'Approved. Enjoy your time off.'
        }
        res_decision = self.client.post(reverse('manager_decision_action', kwargs={'leave_id': leave_req.id}), decision_data)
        self.assertRedirects(res_decision, reverse('manager_leave_approvals'))

        leave_req.refresh_from_db()
        self.assertEqual(leave_req.status, LeaveRequest.Status.APPROVED)
        self.assertEqual(leave_req.approved_by_manager, self.manager)

        # Step 4: Verify attendance records created for the leave dates
        att_start = Attendance.objects.filter(user=self.staff_eng, date=start).first()
        self.assertIsNotNone(att_start)
        self.assertEqual(att_start.status, Attendance.Status.ON_LEAVE)

    def test_department_manager_access_boundary(self):
        # Dept Manager of Engineering CANNOT review leaves from Creative department
        today = date.today()
        leave_creative = LeaveRequest.objects.create(
            user=self.staff_creative,
            leave_type=LeaveRequest.LeaveType.SICK,
            start_date=today,
            end_date=today + timedelta(days=1),
            reason='Flu recovery',
            status=LeaveRequest.Status.PENDING_DEPT_REVIEW
        )

        self.client.force_login(self.dept_mgr_eng)
        res_review = self.client.post(
            reverse('dept_manager_review_action', kwargs={'leave_id': leave_creative.id}),
            {'action': 'RECOMMEND', 'notes': 'Trying to review another dept'}
        )
        self.assertEqual(res_review.status_code, 403)  # Permission Denied

    def test_monthly_reports_access_restriction(self):
        # Level 4 Staff: Forbidden / redirected from monthly reports
        self.client.force_login(self.staff_eng)
        res_staff = self.client.get(reverse('attendance_monthly_reports'))
        self.assertRedirects(res_staff, reverse('attendance_hub'))

        # Level 3 Dept Manager: Forbidden / redirected from monthly reports
        self.client.force_login(self.dept_mgr_eng)
        res_dept = self.client.get(reverse('attendance_monthly_reports'))
        self.assertRedirects(res_dept, reverse('attendance_hub'))

        # Level 2 HR: Allowed
        self.client.force_login(self.hr)
        res_hr = self.client.get(reverse('attendance_monthly_reports'))
        self.assertEqual(res_hr.status_code, 200)
        self.assertContains(res_hr, "Monthly Attendance Ledger")

        # Level 2 Manager: Allowed
        self.client.force_login(self.manager)
        res_mgr = self.client.get(reverse('attendance_monthly_reports'))
        self.assertEqual(res_mgr.status_code, 200)

        # Excel Export test
        res_excel = self.client.get(reverse('attendance_export_excel'))
        self.assertEqual(res_excel.status_code, 200)
        self.assertEqual(res_excel['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        # PDF Export test
        res_pdf = self.client.get(reverse('attendance_export_pdf'))
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')
