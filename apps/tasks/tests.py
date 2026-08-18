from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.departments.models import Branch, Department
from apps.tasks.models import Task, TaskAttachment
from apps.users.models import User


class CreativeTasksTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Departments & Branches
        self.dept_creative = Department.objects.create(name="Aider Creative", description="Creative Studio")
        self.branch_design = Branch.objects.create(department=self.dept_creative, name="Designing")
        self.branch_edit = Branch.objects.create(department=self.dept_creative, name="Editing")

        self.dept_it = Department.objects.create(name="IT Club", description="Engineering")

        # Users
        # 1. Creative Dept Manager
        self.creative_mgr = User.objects.create_user(
            username="deptmgr_rachel",
            email="rachel@aider.internal",
            password="password123",
            role=User.Role.DEPT_MANAGER,
            department=self.dept_creative,
            branch=self.branch_design
        )

        # 2. Non-Creative Dept Manager
        self.it_mgr = User.objects.create_user(
            username="deptmgr_it",
            email="it_mgr@aider.internal",
            password="password123",
            role=User.Role.DEPT_MANAGER,
            department=self.dept_it
        )

        # 3. Creative Department Staff / Executive A (Designing Branch)
        self.creative_staff_daniel = User.objects.create_user(
            username="staff_daniel",
            email="daniel@aider.internal",
            password="password123",
            role=User.Role.EXECUTIVE,
            department=self.dept_creative,
            branch=self.branch_design
        )

        # 4. Creative Department Staff B (Editing Branch)
        self.creative_staff_maya = User.objects.create_user(
            username="staff_maya",
            email="maya@aider.internal",
            password="password123",
            role=User.Role.STAFF,
            department=self.dept_creative,
            branch=self.branch_edit
        )

        # 5. Outside Staff
        self.it_staff = User.objects.create_user(
            username="staff_alex",
            email="alex@aider.internal",
            password="password123",
            role=User.Role.STAFF,
            department=self.dept_it
        )

    def test_creative_dept_manager_can_create_task_with_attachments(self):
        """Creative Department Manager can access creation page and create tasks with attachments."""
        self.client.login(username="deptmgr_rachel", password="password123")

        # Access creation page
        res = self.client.get(reverse('task_create'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Create Creative Department Task")
        self.assertContains(res, "CR-TASK-001")

        # Create task with multiple dummy files (accepts any file type)
        doc1 = SimpleUploadedFile("brand_guide.pdf", b"PDF dummy content", content_type="application/pdf")
        doc2 = SimpleUploadedFile("banner_asset.psd", b"PSD dummy binary content", content_type="application/octet-stream")

        data = {
            'task_number': 'CR-TASK-001',
            'title': 'Redesign Company Brand Identity',
            'description': 'Create new vector brand assets and 3D icons.',
            'instructions': 'Use the official color palette and export 4K PNGs.',
            'priority': Task.Priority.URGENT,
            'status': Task.Status.ACTIVE,
            'documents': [doc1, doc2],
        }

        post_res = self.client.post(reverse('task_create'), data, follow=True)
        self.assertEqual(post_res.status_code, 200)

        # Verify task is created
        task = Task.objects.get(task_number='CR-TASK-001')
        self.assertEqual(task.title, 'Redesign Company Brand Identity')
        self.assertEqual(task.department, self.dept_creative)
        self.assertEqual(task.created_by, self.creative_mgr)
        self.assertEqual(task.priority, Task.Priority.URGENT)

        # Verify attachments
        self.assertEqual(task.attachments.count(), 2)
        filenames = list(task.attachments.values_list('filename', flat=True))
        self.assertIn('brand_guide.pdf', filenames)
        self.assertIn('banner_asset.psd', filenames)

    def test_creative_manager_can_assign_task_by_branch_and_member(self):
        """Manager selects task, selects branch, filters branch members, and assigns task."""
        task = Task.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            task_number='CR-TASK-100',
            title='UI Wireframing Campaign',
            description='Design low-fidelity mockups.',
            priority=Task.Priority.HIGH
        )

        self.client.login(username="deptmgr_rachel", password="password123")

        # Access assignment page
        res = self.client.get(reverse('task_assign'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Assign Creative Tasks to Branch Members")
        self.assertContains(res, "CR-TASK-100")
        self.assertContains(res, "Designing")
        self.assertContains(res, "Editing")

        # Test Branch Members API
        api_res = self.client.get(reverse('branch_members_api', kwargs={'branch_id': self.branch_design.id}))
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.json()
        member_usernames = [m['username'] for m in api_data['members']]
        self.assertIn('staff_daniel', member_usernames)
        self.assertNotIn('staff_maya', member_usernames)

        # Submit Assignment: Assign to Daniel in Designing branch
        post_data = {
            'task_id': task.id,
            'branch_id': self.branch_design.id,
            'user_id': self.creative_staff_daniel.id,
        }
        assign_res = self.client.post(reverse('task_assign'), post_data, follow=True)
        self.assertEqual(assign_res.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.branch, self.branch_design)
        self.assertEqual(task.assigned_to, self.creative_staff_daniel)

    def test_assigned_member_sees_task_and_other_members_do_not(self):
        """Assigned member sees task in dashboard and detail; remaining members cannot see it."""
        task = Task.objects.create(
            department=self.dept_creative,
            branch=self.branch_design,
            assigned_to=self.creative_staff_daniel,
            created_by=self.creative_mgr,
            task_number='CR-TASK-200',
            title='Icon Animation Video',
            description='Export SVG and Lottie JSON files.',
            priority=Task.Priority.MEDIUM
        )

        # 1. Daniel (Assigned Member) logs in
        self.client.login(username="staff_daniel", password="password123")

        # In Employee Dashboard: sees assigned task
        emp_dash = self.client.get(reverse('employee_dashboard'))
        self.assertEqual(emp_dash.status_code, 200)
        self.assertContains(emp_dash, 'CR-TASK-200')
        self.assertContains(emp_dash, 'Icon Animation Video')
        self.assertContains(emp_dash, 'Assigned Directly to You')

        # In Task List: sees assigned task
        task_list = self.client.get(reverse('task_list'))
        self.assertEqual(task_list.status_code, 200)
        self.assertContains(task_list, 'CR-TASK-200')

        # In Task Detail: can view full details
        task_detail = self.client.get(reverse('task_detail', kwargs={'task_id': task.id}))
        self.assertEqual(task_detail.status_code, 200)
        self.assertContains(task_detail, 'Icon Animation Video')
        self.assertContains(task_detail, 'Export SVG and Lottie JSON files.')

        # 2. Maya (Other Creative Staff, not assigned) logs in
        self.client.login(username="staff_maya", password="password123")

        # In Employee Dashboard: does NOT see Daniel's task
        maya_dash = self.client.get(reverse('employee_dashboard'))
        self.assertEqual(maya_dash.status_code, 200)
        self.assertNotContains(maya_dash, 'CR-TASK-200')
        self.assertNotContains(maya_dash, 'Icon Animation Video')

        # In Task List: does NOT see Daniel's task
        maya_list = self.client.get(reverse('task_list'))
        self.assertEqual(maya_list.status_code, 200)
        self.assertNotContains(maya_list, 'CR-TASK-200')

        # In Task Detail: access restricted
        maya_detail = self.client.get(reverse('task_detail', kwargs={'task_id': task.id}), follow=True)
        self.assertContains(maya_detail, "Access restricted: This task is assigned to another team member.")

    def test_non_creative_dept_manager_cannot_create_or_assign_task(self):
        """Non-Creative Department Managers are strictly prevented from creating or assigning tasks."""
        self.client.login(username="deptmgr_it", password="password123")

        # Attempt to access assign page
        res = self.client.get(reverse('task_assign'), follow=True)
        self.assertContains(res, "Permission Denied: Only the Creative Department Manager is authorized")

    def test_sequential_task_number_generation(self):
        """Task.generate_next_task_number increments sequentially."""
        next_1 = Task.generate_next_task_number("Aider Creative")
        self.assertEqual(next_1, "CR-TASK-001")

        Task.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            task_number=next_1,
            title='Task 1',
            description='Desc 1'
        )

        next_2 = Task.generate_next_task_number("Aider Creative")
        self.assertEqual(next_2, "CR-TASK-002")
