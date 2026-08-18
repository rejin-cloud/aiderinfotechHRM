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

        # 3. Creative Department Staff / Executive (Member)
        self.creative_staff = User.objects.create_user(
            username="staff_daniel",
            email="daniel@aider.internal",
            password="password123",
            role=User.Role.EXECUTIVE,
            department=self.dept_creative,
            branch=self.branch_design
        )

        # 4. Outside Staff
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

    def test_non_creative_dept_manager_cannot_create_task(self):
        """Non-Creative Department Managers are strictly prevented from creating tasks in Creative Dept."""
        self.client.login(username="deptmgr_it", password="password123")

        res = self.client.get(reverse('task_create'), follow=True)
        # Should redirect with error
        self.assertContains(res, "Permission Denied: Only the Creative Department Manager is authorized")

        # Attempt direct POST
        post_res = self.client.post(reverse('task_create'), {
            'task_number': 'CR-TASK-999',
            'title': 'Unauthorized Task',
            'description': 'Trying to create without permission',
            'priority': Task.Priority.HIGH,
            'status': Task.Status.ACTIVE,
        }, follow=True)
        self.assertFalse(Task.objects.filter(task_number='CR-TASK-999').exists())

    def test_creative_member_cannot_create_or_edit_task(self):
        """Creative department staff/interns cannot create, edit, or delete tasks."""
        self.client.login(username="staff_daniel", password="password123")

        # 1. Attempt task creation
        res = self.client.get(reverse('task_create'), follow=True)
        self.assertContains(res, "Permission Denied: Only the Creative Department Manager is authorized")

        # Create a task as manager first
        task = Task.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            task_number='CR-TASK-010',
            title='Icon Set Production',
            description='Design 15 system icons.',
            priority=Task.Priority.MEDIUM
        )

        # 2. Attempt task edit as staff
        edit_res = self.client.post(reverse('task_edit', kwargs={'task_id': task.id}), {
            'task_number': 'CR-TASK-010',
            'title': 'Hacked Title',
            'description': 'Hacked description',
            'priority': Task.Priority.LOW,
            'status': Task.Status.ACTIVE,
        }, follow=True)
        self.assertContains(edit_res, "Permission Denied")
        task.refresh_from_db()
        self.assertEqual(task.title, 'Icon Set Production')

        # 3. Attempt task delete as staff
        del_res = self.client.post(reverse('task_delete', kwargs={'task_id': task.id}), follow=True)
        self.assertContains(del_res, "Permission Denied")
        self.assertTrue(Task.objects.filter(id=task.id).exists())

    def test_creative_member_can_view_task_read_only(self):
        """Creative department staff can view tasks in read-only mode."""
        task = Task.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            task_number='CR-TASK-020',
            title='Motion Graphics Reel',
            description='Edit 30-second promo video.',
            instructions='1080x1920 60fps export required.',
            priority=Task.Priority.HIGH
        )

        doc = SimpleUploadedFile("script.docx", b"Script word file content", content_type="application/msword")
        TaskAttachment.objects.create(task=task, file=doc)

        self.client.login(username="staff_daniel", password="password123")

        # 1. Task List
        list_res = self.client.get(reverse('task_list'))
        self.assertEqual(list_res.status_code, 200)
        self.assertContains(list_res, 'CR-TASK-020')
        self.assertContains(list_res, 'Motion Graphics Reel')
        # Manager controls should not appear for staff
        self.assertNotContains(list_res, 'Create New Task')

        # 2. Task Detail
        detail_res = self.client.get(reverse('task_detail', kwargs={'task_id': task.id}))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, 'Motion Graphics Reel')
        self.assertContains(detail_res, '1080x1920 60fps export required.')
        self.assertContains(detail_res, 'script.docx')
        self.assertContains(detail_res, 'Read-Only Member View')
        self.assertNotContains(detail_res, 'Edit Task & Files')

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
