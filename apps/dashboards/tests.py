from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.users.models import User
from apps.departments.models import Department, Branch
from apps.attendance.models import Attendance, LeaveRequest
from apps.tasks.models import Client as ExternalClient

class DeptManagerDashboardTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Departments
        self.it_dept = Department.objects.create(name='IT Club', description='Technical and Software Development')
        self.creative_dept = Department.objects.create(name='Aider Creative', description='Media, Marketing, Creative Studio')

        # Branches
        self.it_branch_1 = Branch.objects.create(department=self.it_dept, name='IT Club Balussery', location='Balussery Tech Center')
        self.it_branch_2 = Branch.objects.create(department=self.it_dept, name='IT Club Calicut', location='Calicut Cyberpark')
        self.creative_branch = Branch.objects.create(department=self.creative_dept, name='Designing', location='Creative Block')

        # IT Department Manager (Supervises all IT branches)
        self.it_dept_manager = User.objects.create_user(
            username='it_dept_mgr',
            password='password123',
            role=User.Role.DEPT_MANAGER,
            department=self.it_dept,
            branch=None,
            employee_id='EMP-IT-001',
            first_name='Alan',
            last_name='Turing'
        )

        self.creative_dept_manager = User.objects.create_user(
            username='creative_dept_mgr',
            password='password123',
            role=User.Role.DEPT_MANAGER,
            department=self.creative_dept,
            branch=self.creative_branch,
            employee_id='EMP-CR-001',
            first_name='Leonardo',
            last_name='Vinci'
        )

        # IT Subordinates across branches
        self.it_exec = User.objects.create_user(
            username='it_exec',
            password='password123',
            role=User.Role.EXECUTIVE,
            department=self.it_dept,
            branch=self.it_branch_1,
            employee_id='EMP-IT-002',
            first_name='Grace',
            last_name='Hopper',
            designation='Lead Cloud Architect'
        )

        self.it_intern = User.objects.create_user(
            username='it_intern',
            password='password123',
            role=User.Role.INTERN,
            department=self.it_dept,
            branch=self.it_branch_2,
            employee_id='EMP-IT-003',
            first_name='Linus',
            last_name='Torvalds',
            designation='Junior Kernel Intern'
        )

        # Today's attendance
        today = timezone.localdate()
        Attendance.objects.create(
            user=self.it_exec,
            date=today,
            status=Attendance.Status.PRESENT
        )

    def test_it_club_dept_manager_dashboard_renders_clean_and_exclusive_to_it(self):
        self.client.login(username='it_dept_mgr', password='password123')
        url = reverse('dept_manager_dashboard')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_it_club'])
        self.assertFalse(response.context['is_creative'])

        # Verify page title and header
        self.assertContains(response, 'IT Club Operations')
        self.assertContains(response, 'Engineering Command Center')
        
        # Verify IT branch hubs exist
        self.assertContains(response, 'IT Club Balussery')
        self.assertContains(response, 'IT Club Calicut')

        # Verify IT subordinates exist
        self.assertContains(response, 'Grace Hopper')
        self.assertContains(response, 'Linus Torvalds')
        self.assertContains(response, 'Lead Cloud Architect')
        self.assertContains(response, 'Junior Kernel Intern')

        # Verify NO Creative or Academy items leak into IT Club dashboard
        content = response.content.decode('utf-8')
        self.assertNotIn('Creative Tasks Pipeline', content)
        self.assertNotIn('Creative Studio Tasks', content)
        self.assertNotIn('Creative Operations Calendar', content)
        self.assertNotIn('Aider Academy', content)

    def test_creative_dept_manager_dashboard_renders_creative_workflows(self):
        self.client.login(username='creative_dept_mgr', password='password123')
        url = reverse('dept_manager_dashboard')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_it_club'])
        self.assertTrue(response.context['is_creative'])

        # Verify Creative workflows render
        self.assertContains(response, 'Creative Tasks Pipeline')
        self.assertContains(response, 'Corporate Clients Registry')
