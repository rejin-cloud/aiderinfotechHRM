from django.test import TestCase, Client
from django.urls import reverse
from apps.users.models import User
from apps.departments.models import Department, Branch

class EndpointIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Aider Creative")
        self.branch = Branch.objects.create(department=self.dept, name="Designing")
        
        self.superadmin = User.objects.create_user(
            username="test_superadmin",
            password="password123",
            role=User.Role.SUPERADMIN
        )
        self.manager = User.objects.create_user(
            username="test_manager",
            password="password123",
            role=User.Role.MANAGER,
            department=self.dept
        )
        self.hr = User.objects.create_user(
            username="test_hr",
            password="password123",
            role=User.Role.HR,
            department=self.dept
        )
        self.dept_mgr = User.objects.create_user(
            username="test_deptmgr",
            password="password123",
            role=User.Role.DEPT_MANAGER,
            department=self.dept,
            branch=self.branch
        )
        self.employee = User.objects.create_user(
            username="test_employee",
            password="password123",
            role=User.Role.EXECUTIVE,
            department=self.dept,
            branch=self.branch
        )

    def test_login_page(self):
        res = self.client.get(reverse('login'))
        self.assertEqual(res.status_code, 200)

    def test_superadmin_flow_and_dashboard(self):
        self.client.force_login(self.superadmin)
        res = self.client.get(reverse('dashboard_router'))
        self.assertRedirects(res, reverse('superadmin_dashboard'))
        
        dashboard_res = self.client.get(reverse('superadmin_dashboard'))
        self.assertEqual(dashboard_res.status_code, 200)

    def test_manager_flow_and_dashboard(self):
        self.client.force_login(self.manager)
        res = self.client.get(reverse('dashboard_router'))
        self.assertRedirects(res, reverse('manager_dashboard'))
        
        dashboard_res = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(dashboard_res.status_code, 200)

    def test_hr_flow_and_dashboard(self):
        self.client.force_login(self.hr)
        res = self.client.get(reverse('dashboard_router'))
        self.assertRedirects(res, reverse('hr_dashboard'))
        
        dashboard_res = self.client.get(reverse('hr_dashboard'))
        self.assertEqual(dashboard_res.status_code, 200)

    def test_dept_manager_flow_and_dashboard(self):
        self.client.force_login(self.dept_mgr)
        res = self.client.get(reverse('dashboard_router'))
        self.assertRedirects(res, reverse('dept_manager_dashboard'))
        
        dashboard_res = self.client.get(reverse('dept_manager_dashboard'))
        self.assertEqual(dashboard_res.status_code, 200)

    def test_employee_flow_and_dashboard(self):
        self.client.force_login(self.employee)
        res = self.client.get(reverse('dashboard_router'))
        self.assertRedirects(res, reverse('employee_dashboard'))
        
        dashboard_res = self.client.get(reverse('employee_dashboard'))
        self.assertEqual(dashboard_res.status_code, 200)

    def test_department_creation_restricted(self):
        # Manager is NOT allowed to create department
        self.client.force_login(self.manager)
        res = self.client.post(reverse('department_create'), {'name': 'New Dept'})
        # Should redirect with error
        self.assertRedirects(res, reverse('department_list'))

        # Superadmin IS allowed to create department
        self.client.force_login(self.superadmin)
        res_super = self.client.post(reverse('department_create'), {'name': 'New Valid Dept', 'description': 'Test'})
        self.assertEqual(res_super.status_code, 302)
        self.assertTrue(Department.objects.filter(name='New Valid Dept').exists())

    def test_branch_creation_by_manager(self):
        # Manager IS allowed to create branch
        self.client.force_login(self.manager)
        res = self.client.post(reverse('branch_create'), {
            'department': self.dept.id,
            'name': 'Manager Created Branch',
            'location': 'Wing B'
        })
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Branch.objects.filter(name='Manager Created Branch').exists())

    def test_excel_export_download(self):
        self.client.force_login(self.superadmin)
        res = self.client.get(reverse('export_excel'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', res['Content-Type'])

    def test_pdf_export_download(self):
        self.client.force_login(self.superadmin)
        res = self.client.get(reverse('export_pdf'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('application/pdf', res['Content-Type'])

    def test_my_dossier_download(self):
        self.client.force_login(self.employee)
        res = self.client.get(reverse('export_my_dossier'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('application/pdf', res['Content-Type'])

    def test_registration_page_get(self):
        res = self.client.get(reverse('register'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Create an Account")
        self.assertContains(res, "Aider Creative")

    def test_registration_submission_success(self):
        post_data = {
            'username': 'newuser123',
            'email': 'newuser@example.com',
            'phone': '+1 555-123-4567',
            'department': self.dept.id,
            'password': 'password123',
            'confirm_password': 'password123'
        }
        res = self.client.post(reverse('register'), post_data)
        self.assertRedirects(res, reverse('login'))
        self.assertTrue(User.objects.filter(username='newuser123').exists())
        user = User.objects.get(username='newuser123')
        self.assertEqual(user.email, 'newuser@example.com')
        self.assertEqual(user.phone, '+1 555-123-4567')
        self.assertEqual(user.department, self.dept)
        self.assertEqual(user.designation, 'Staff / Employee')
        self.assertEqual(user.role, User.Role.STAFF)
        self.assertTrue(user.check_password('password123'))

        # Log in as newly registered user and verify employee dashboard
        self.client.force_login(user)
        dash_res = self.client.get(reverse('dashboard_router'))
        self.assertRedirects(dash_res, reverse('employee_dashboard'))
        emp_dash_res = self.client.get(reverse('employee_dashboard'))
        self.assertEqual(emp_dash_res.status_code, 200)
        self.assertContains(emp_dash_res, "Staff / Employee")
        self.assertContains(emp_dash_res, "Aider Creative")
        self.assertContains(emp_dash_res, "Aider Infotech Overview")

    def test_assign_employee_access_restriction(self):
        # Non-superadmin is rejected
        self.client.force_login(self.employee)
        res = self.client.get(reverse('assign_employee'))
        self.assertRedirects(res, reverse('dashboard_router'), target_status_code=302)

        # Superadmin has full access
        self.client.force_login(self.superadmin)
        res_super = self.client.get(reverse('assign_employee'))
        self.assertEqual(res_super.status_code, 200)
        self.assertContains(res_super, "Dedicated Employee Assignment Hub")

    def test_superadmin_assigns_employee_to_server_admin(self):
        # Create a new registered staff employee
        newbie = User.objects.create_user(
            username="newbie_dev",
            password="password123",
            role=User.Role.STAFF,
            department=self.dept,
            designation="Staff / Employee"
        )
        # Superadmin assigns newbie to Server Admin role
        self.client.force_login(self.superadmin)
        post_data = {
            'user_id': newbie.id,
            'role': User.Role.SERVER_ADMIN,
            'department': self.dept.id,
            'branch': self.branch.id,
            'designation': 'Principal Server Architect'
        }
        assign_res = self.client.post(reverse('assign_specific_employee', kwargs={'user_id': newbie.id}), post_data)
        self.assertRedirects(assign_res, reverse('superadmin_dashboard'))

        # Verify updated in DB
        newbie.refresh_from_db()
        self.assertEqual(newbie.role, User.Role.SERVER_ADMIN)
        self.assertEqual(newbie.department, self.dept)
        self.assertEqual(newbie.branch, self.branch)
        self.assertEqual(newbie.designation, 'Principal Server Architect')
        self.assertTrue(newbie.is_staff)

        # Verify next login redirects to Server Admin dashboard
        self.client.force_login(newbie)
        route_res = self.client.get(reverse('dashboard_router'))
        self.assertRedirects(route_res, reverse('serveradmin_dashboard'))
        server_dash_res = self.client.get(reverse('serveradmin_dashboard'))
        self.assertEqual(server_dash_res.status_code, 200)
        self.assertContains(server_dash_res, "Server Admin Dashboard")
        self.assertContains(server_dash_res, "Server Architecture & Topology")


    def test_superadmin_assigns_employee_to_manager(self):
        newbie = User.objects.create_user(
            username="newbie_mgr",
            password="password123",
            role=User.Role.STAFF,
            department=self.dept
        )
        self.client.force_login(self.superadmin)
        post_data = {
            'user_id': newbie.id,
            'role': User.Role.MANAGER,
            'department': self.dept.id,
            'branch': '',
            'designation': 'Creative Department General Manager'
        }
        self.client.post(reverse('assign_specific_employee', kwargs={'user_id': newbie.id}), post_data)
        newbie.refresh_from_db()
        self.assertEqual(newbie.role, User.Role.MANAGER)

        # Next login routes to manager dashboard
        self.client.force_login(newbie)
        route_res = self.client.get(reverse('dashboard_router'))
        self.assertRedirects(route_res, reverse('manager_dashboard'))



