import datetime
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.departments.models import Branch, Department
from apps.tasks.models import (
    Client as ClientModel,
    ClientAssignment,
    Task,
    TaskAttachment,
    TaskExtensionRequest,
    TaskSubmission,
    TaskSubmissionAttachment,
)
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
            first_name="Rachel",
            last_name="Green",
            email="rachel@aider.internal",
            password="password123",
            role=User.Role.DEPT_MANAGER,
            department=self.dept_creative,
            branch=self.branch_design
        )

        # 2. Non-Creative Dept Manager
        self.it_mgr = User.objects.create_user(
            username="deptmgr_it",
            first_name="Ian",
            last_name="Torvalds",
            email="it_mgr@aider.internal",
            password="password123",
            role=User.Role.DEPT_MANAGER,
            department=self.dept_it
        )

        # 3. Creative Department Staff / Executive A (Designing Branch - Assignee)
        self.creative_staff_daniel = User.objects.create_user(
            username="staff_daniel",
            first_name="Daniel",
            last_name="Craig",
            email="daniel@aider.internal",
            password="password123",
            role=User.Role.EXECUTIVE,
            department=self.dept_creative,
            branch=self.branch_design
        )

        # 4. Creative Department Staff B (Designing Branch - Non-Assigned Member of Same Branch)
        self.creative_staff_liam = User.objects.create_user(
            username="staff_liam",
            first_name="Liam",
            last_name="Neeson",
            email="liam@aider.internal",
            password="password123",
            role=User.Role.STAFF,
            department=self.dept_creative,
            branch=self.branch_design
        )

        # 5. Creative Department Staff C (Editing Branch - Different Branch)
        self.creative_staff_maya = User.objects.create_user(
            username="staff_maya",
            first_name="Maya",
            last_name="Lin",
            email="maya@aider.internal",
            password="password123",
            role=User.Role.STAFF,
            department=self.dept_creative,
            branch=self.branch_edit
        )

        # 6. Creative Department Executive B (Editing Branch)
        self.creative_exec_edit = User.objects.create_user(
            username="exec_eric",
            first_name="Eric",
            last_name="Bana",
            email="eric@aider.internal",
            password="password123",
            role=User.Role.EXECUTIVE,
            department=self.dept_creative,
            branch=self.branch_edit
        )

        # 7. Creative Department Intern (Designing Branch)
        self.creative_intern_sam = User.objects.create_user(
            username="intern_sam",
            first_name="Sam",
            last_name="Smith",
            email="sam@aider.internal",
            password="password123",
            role=User.Role.INTERN,
            department=self.dept_creative,
            branch=self.branch_design
        )

        # 8. Outside Staff
        self.it_staff = User.objects.create_user(
            username="staff_alex",
            first_name="Alex",
            last_name="Ferguson",
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
        self.assertContains(res, "Assign Creative Tasks")
        self.assertContains(res, "CR-TASK-100")
        self.assertContains(res, "Designing")
        self.assertContains(res, "Editing")

        # Test Branch Members API
        api_res = self.client.get(reverse('branch_members_api', kwargs={'branch_id': self.branch_design.id}))
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.json()
        member_usernames = [m['username'] for m in api_data['members']]
        self.assertIn('staff_daniel', member_usernames)
        self.assertIn('staff_liam', member_usernames)
        self.assertNotIn('staff_maya', member_usernames)

        # Submit Assignment: Assign to Daniel in Designing branch with a completion deadline
        post_data = {
            'task_id': task.id,
            'branch_id': self.branch_design.id,
            'user_id': self.creative_staff_daniel.id,
            'deadline': '2026-08-25T18:00',
        }
        assign_res = self.client.post(reverse('task_assign'), post_data, follow=True)
        self.assertEqual(assign_res.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.branch, self.branch_design)
        self.assertEqual(task.assigned_to, self.creative_staff_daniel)
        self.assertIsNotNone(task.deadline)
        self.assertEqual(task.deadline.year, 2026)
        self.assertEqual(task.deadline.month, 8)
        self.assertEqual(task.deadline.day, 25)

    def test_branch_member_visibility_and_assignment_privacy(self):
        """
        - Task assigned to Designing branch & Daniel Craig.
        - Daniel (Assignee) sees task and sees 'Assigned to You'.
        - Liam (Other member of Designing branch) sees task, can read brief & assets, but CANNOT see who it is assigned to.
        - Maya (Editing branch member) cannot see this task.
        """
        task = Task.objects.create(
            department=self.dept_creative,
            branch=self.branch_design,
            assigned_to=self.creative_staff_daniel,
            created_by=self.creative_mgr,
            task_number='CR-TASK-300',
            title='Vector 3D Illustration Pack',
            description='Produce 3D isometric tech illustrations.',
            instructions='Export in PNG and SVG at 300 DPI.',
            priority=Task.Priority.HIGH
        )

        # 1. Daniel (Assigned Member in Designing branch)
        self.client.login(username="staff_daniel", password="password123")

        # Dashboard: sees task with "Assigned Directly to You"
        dash_res = self.client.get(reverse('employee_dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, 'CR-TASK-300')
        self.assertContains(dash_res, 'Assigned Directly to You')

        # Task List: sees task with "Assigned to You"
        list_res = self.client.get(reverse('task_list'))
        self.assertEqual(list_res.status_code, 200)
        self.assertContains(list_res, 'CR-TASK-300')
        self.assertContains(list_res, 'Assigned to You')

        # Task Detail: can view full details
        detail_res = self.client.get(reverse('task_detail', kwargs={'task_id': task.id}))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, 'Assigned to You')
        self.assertContains(detail_res, 'Export in PNG and SVG at 300 DPI.')

        # 2. Liam (Same branch: Designing, but NOT assigned)
        self.client.login(username="staff_liam", password="password123")

        # Dashboard: sees the branch task, but does NOT see who it is assigned to
        liam_dash = self.client.get(reverse('employee_dashboard'))
        self.assertEqual(liam_dash.status_code, 200)
        self.assertContains(liam_dash, 'CR-TASK-300')
        self.assertContains(liam_dash, 'Vector 3D Illustration Pack')
        self.assertContains(liam_dash, 'Branch Directive')
        self.assertNotContains(liam_dash, 'Assigned Directly to You')

        # Task List: sees the branch task, but no assignment pill
        liam_list = self.client.get(reverse('task_list'))
        self.assertEqual(liam_list.status_code, 200)
        self.assertContains(liam_list, 'CR-TASK-300')
        self.assertContains(liam_list, 'Designing')
        self.assertNotContains(liam_list, 'Assigned to You')
        self.assertNotContains(liam_list, 'Assigned Directly to You')

        # Task Detail: can read instructions & scope, but cannot see who it is assigned to
        liam_detail = self.client.get(reverse('task_detail', kwargs={'task_id': task.id}))
        self.assertEqual(liam_detail.status_code, 200)
        self.assertContains(liam_detail, 'Produce 3D isometric tech illustrations.')
        self.assertContains(liam_detail, 'Export in PNG and SVG at 300 DPI.')
        self.assertContains(liam_detail, 'Branch Directive: <strong>Designing</strong>')
        self.assertNotContains(liam_detail, 'Assigned Member:')
        self.assertNotContains(liam_detail, 'Assigned to You')
        self.assertNotContains(liam_detail, 'Assigned Directly to You')

        # 3. Maya (Different branch: Editing)
        self.client.login(username="staff_maya", password="password123")

        # Dashboard: does not see Designing branch task
        maya_dash = self.client.get(reverse('employee_dashboard'))
        self.assertEqual(maya_dash.status_code, 200)
        self.assertNotContains(maya_dash, 'CR-TASK-300')

        # Task List: does not see Designing branch task
        maya_list = self.client.get(reverse('task_list'))
        self.assertEqual(maya_list.status_code, 200)
        self.assertNotContains(maya_list, 'CR-TASK-300')

        # Task Detail: access restricted
        maya_detail = self.client.get(reverse('task_detail', kwargs={'task_id': task.id}), follow=True)
        self.assertContains(maya_detail, "Access restricted: This task belongs to another branch.")

    def test_assigned_member_submits_deliverables_and_manager_marks_completed(self):
        """
        - Member can ONLY submit deliverables (status moves to UNDER_REVIEW, NOT COMPLETED).
        - Creative Department Manager reviews deliverables and marks COMPLETED.
        """
        task = Task.objects.create(
            department=self.dept_creative,
            branch=self.branch_design,
            assigned_to=self.creative_staff_daniel,
            created_by=self.creative_mgr,
            task_number='CR-TASK-400',
            title='Social Media Motion Graphics',
            description='Create 3 animated reels for product launch.',
            priority=Task.Priority.HIGH,
            status=Task.Status.ACTIVE
        )

        self.client.login(username="staff_daniel", password="password123")

        # Access submit page
        res = self.client.get(reverse('task_complete', kwargs={'task_id': task.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Submit Deliverables for Review")

        # Member submits deliverables
        file1 = SimpleUploadedFile("reel_final.mp4", b"MP4 dummy video bytes", content_type="video/mp4")
        file2 = SimpleUploadedFile("assets.zip", b"ZIP archive bytes", content_type="application/zip")

        post_data = {
            'remarks': 'Completed all 3 reels with audio mixing and color grade at 1080x1920.',
            'submission_files': [file1, file2],
        }

        post_res = self.client.post(reverse('task_complete', kwargs={'task_id': task.id}), post_data, follow=True)
        self.assertEqual(post_res.status_code, 200)
        self.assertContains(post_res, "Under Manager Review")

        # Task is in UNDER_REVIEW (NOT COMPLETED!)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.UNDER_REVIEW)
        self.assertIsNone(task.completed_at)

        # Submission is pending review
        self.assertEqual(task.submissions.count(), 1)
        sub = task.submissions.first()
        self.assertEqual(sub.submitted_by, self.creative_staff_daniel)
        self.assertEqual(sub.review_status, TaskSubmission.ReviewStatus.PENDING)
        self.assertEqual(sub.attachments.count(), 2)

        # 2. Manager reviews deliverables and approves -> marks COMPLETED
        self.client.login(username="deptmgr_rachel", password="password123")

        review_page = self.client.get(reverse('manager_submission_review', kwargs={'task_id': task.id}))
        self.assertEqual(review_page.status_code, 200)
        self.assertContains(review_page, "Evaluate Submitted Deliverables")
        self.assertContains(review_page, "reel_final.mp4")

        # Manager approves
        approve_post = self.client.post(
            reverse('manager_submission_review', kwargs={'task_id': task.id}),
            {
                'decision': 'APPROVE',
                'manager_feedback': 'Great color grading and sound design! Approved.',
            },
            follow=True
        )
        self.assertEqual(approve_post.status_code, 200)

        task.refresh_from_db()
        sub.refresh_from_db()

        self.assertEqual(task.status, Task.Status.COMPLETED)
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(sub.review_status, TaskSubmission.ReviewStatus.APPROVED)
        self.assertEqual(sub.reviewed_by, self.creative_mgr)

    def test_manager_can_request_revision_and_member_resubmits(self):
        """
        - Member submits deliverables.
        - Manager requests revision if not good enough (task returns to ACTIVE with feedback).
        - Member sees feedback and submits revised deliverables.
        """
        task = Task.objects.create(
            department=self.dept_creative,
            branch=self.branch_design,
            assigned_to=self.creative_staff_daniel,
            created_by=self.creative_mgr,
            task_number='CR-TASK-401',
            title='Product Catalog Layout',
            description='Design 16-page catalog.',
            status=Task.Status.ACTIVE
        )

        # Member submits 1st draft
        self.client.login(username="staff_daniel", password="password123")
        self.client.post(
            reverse('task_complete', kwargs={'task_id': task.id}),
            {'remarks': 'Draft v1 ready.'}
        )

        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.UNDER_REVIEW)

        # Manager requests revision
        self.client.login(username="deptmgr_rachel", password="password123")
        rev_post = self.client.post(
            reverse('manager_submission_review', kwargs={'task_id': task.id}),
            {
                'decision': 'REVISION',
                'manager_feedback': 'Margins on page 4 and 8 are misaligned. Please fix typography and resubmit.',
                'new_deadline': (timezone.now() + datetime.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),
            },
            follow=True
        )
        self.assertEqual(rev_post.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.ACTIVE)

        # Member views task detail and sees revision request banner
        self.client.login(username="staff_daniel", password="password123")
        detail_res = self.client.get(reverse('task_detail', kwargs={'task_id': task.id}))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, "Revision Requested by Department Manager")
        self.assertContains(detail_res, "Margins on page 4 and 8 are misaligned")

        # Member resubmits v2
        file_v2 = SimpleUploadedFile("catalog_v2.pdf", b"PDF v2 bytes", content_type="application/pdf")
        resub_post = self.client.post(
            reverse('task_complete', kwargs={'task_id': task.id}),
            {
                'remarks': 'Fixed margins and typography alignment.',
                'submission_files': [file_v2]
            },
            follow=True
        )
        self.assertEqual(resub_post.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.UNDER_REVIEW)
        self.assertEqual(task.submissions.count(), 2)

    def test_manager_can_reassign_task_during_submission_review(self):
        """Manager can reassign task to another member during deliverables review."""
        task = Task.objects.create(
            department=self.dept_creative,
            branch=self.branch_design,
            assigned_to=self.creative_staff_daniel,
            created_by=self.creative_mgr,
            task_number='CR-TASK-402',
            title='3D Modeling Scene',
            description='Requires Cinema4D.',
            status=Task.Status.ACTIVE
        )

        # Daniel submits initial attempt
        self.client.login(username="staff_daniel", password="password123")
        self.client.post(
            reverse('task_complete', kwargs={'task_id': task.id}),
            {'remarks': 'Struggling with lighting setup in Blender.'}
        )

        # Manager decides to reassign to Maya in Editing branch
        self.client.login(username="deptmgr_rachel", password="password123")
        reassign_post = self.client.post(
            reverse('manager_submission_review', kwargs={'task_id': task.id}),
            {
                'decision': 'REASSIGN',
                'reassign_branch': self.branch_edit.id,
                'reassign_user': self.creative_staff_maya.id,
                'manager_feedback': 'Reassigning to Maya for advanced lighting and rendering.',
            },
            follow=True
        )
        self.assertEqual(reassign_post.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.branch, self.branch_edit)
        self.assertEqual(task.assigned_to, self.creative_staff_maya)
        self.assertEqual(task.status, Task.Status.ACTIVE)

    def test_overdue_task_automatically_transitions_to_on_hold(self):
        """Active task whose deadline has passed automatically moves to ON_HOLD."""
        past_deadline = timezone.now() - datetime.timedelta(days=2)
        task = Task.objects.create(
            department=self.dept_creative,
            branch=self.branch_design,
            assigned_to=self.creative_staff_daniel,
            created_by=self.creative_mgr,
            task_number='CR-TASK-500',
            title='Overdue Campaign Assets',
            description='Test deadline expiration.',
            priority=Task.Priority.URGENT,
            status=Task.Status.ACTIVE,
            deadline=past_deadline
        )

        self.client.login(username="staff_daniel", password="password123")

        # Accessing task list triggers Task.update_overdue_tasks()
        res = self.client.get(reverse('task_list'))
        self.assertEqual(res.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.ON_HOLD)

    def test_assigned_member_can_request_extension_and_manager_review(self):
        """Assigned member requests more days; Creative Department Manager approves and extends deadline."""
        task = Task.objects.create(
            department=self.dept_creative,
            branch=self.branch_design,
            assigned_to=self.creative_staff_daniel,
            created_by=self.creative_mgr,
            task_number='CR-TASK-600',
            title='3D Billboard Mockup',
            description='Design anamorphic 3D billboard.',
            status=Task.Status.ON_HOLD,
            deadline=timezone.now() - datetime.timedelta(days=1)
        )

        # 1. Member submits extension request
        self.client.login(username="staff_daniel", password="password123")
        req_res = self.client.post(
            reverse('task_request_extension', kwargs={'task_id': task.id}),
            {
                'request_type': TaskExtensionRequest.RequestType.MORE_DAYS,
                'requested_days': 4,
                'reason': '3D ray-tracing rendering is taking additional compute time.',
            },
            follow=True
        )
        self.assertEqual(req_res.status_code, 200)

        ext_req = task.extension_requests.first()
        self.assertIsNotNone(ext_req)
        self.assertEqual(ext_req.status, TaskExtensionRequest.Status.PENDING)
        self.assertEqual(ext_req.requested_days, 4)

        # 2. Manager reviews request and grants extra days
        self.client.login(username="deptmgr_rachel", password="password123")

        queue_res = self.client.get(reverse('manager_extension_requests'))
        self.assertEqual(queue_res.status_code, 200)
        self.assertContains(queue_res, "CR-TASK-600")

        new_target_deadline = timezone.now() + datetime.timedelta(days=4)
        review_post = self.client.post(
            reverse('manager_extension_review', kwargs={'request_id': ext_req.id}),
            {
                'decision': 'EXTEND',
                'new_deadline': new_target_deadline.strftime('%Y-%m-%dT%H:%M'),
                'manager_remarks': 'Approved 4 days extension. Focus on 4K resolution render.',
            },
            follow=True
        )
        self.assertEqual(review_post.status_code, 200)

        task.refresh_from_db()
        ext_req.refresh_from_db()

        self.assertEqual(task.status, Task.Status.ACTIVE)
        self.assertEqual(ext_req.status, TaskExtensionRequest.Status.APPROVED)
        self.assertEqual(ext_req.manager_action, TaskExtensionRequest.ManagerAction.EXTENDED)
        self.assertEqual(ext_req.reviewed_by, self.creative_mgr)

    def test_manager_can_reassign_task_via_extension_review(self):
        """Manager reassigns task to a new branch and member through request review."""
        task = Task.objects.create(
            department=self.dept_creative,
            branch=self.branch_design,
            assigned_to=self.creative_staff_daniel,
            created_by=self.creative_mgr,
            task_number='CR-TASK-700',
            title='Video Color Grading',
            description='Reassign from Designing to Editing branch.',
            status=Task.Status.ON_HOLD,
            deadline=timezone.now() - datetime.timedelta(days=1)
        )

        ext_req = TaskExtensionRequest.objects.create(
            task=task,
            requested_by=self.creative_staff_daniel,
            request_type=TaskExtensionRequest.RequestType.REASSIGN,
            reason='This requires specialized DaVinci Resolve editing skills.',
            status=TaskExtensionRequest.Status.PENDING
        )

        # Manager reassigns to Maya in Editing branch
        self.client.login(username="deptmgr_rachel", password="password123")
        review_post = self.client.post(
            reverse('manager_extension_review', kwargs={'request_id': ext_req.id}),
            {
                'decision': 'REASSIGN',
                'reassign_branch': self.branch_edit.id,
                'reassign_user': self.creative_staff_maya.id,
                'new_deadline': (timezone.now() + datetime.timedelta(days=5)).strftime('%Y-%m-%dT%H:%M'),
                'manager_remarks': 'Reassigned to Maya in Editing branch.',
            },
            follow=True
        )
        self.assertEqual(review_post.status_code, 200)

        task.refresh_from_db()
        ext_req.refresh_from_db()

        self.assertEqual(task.branch, self.branch_edit)
        self.assertEqual(task.assigned_to, self.creative_staff_maya)
        self.assertEqual(task.status, Task.Status.ACTIVE)
        self.assertEqual(ext_req.status, TaskExtensionRequest.Status.APPROVED)
        self.assertEqual(ext_req.manager_action, TaskExtensionRequest.ManagerAction.REASSIGNED)

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

    def test_creative_manager_can_add_and_list_clients(self):
        """Creative Department Manager has dedicated authority to register clients."""
        self.client.login(username="deptmgr_rachel", password="password123")

        # 1. Access Client Create Page
        res_get = self.client.get(reverse('client_create'))
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, "Add New Creative Client")
        self.assertContains(res_get, "CR-CL-001")

        # 2. Submit new client
        post_data = {
            'client_number': 'CR-CL-001',
            'name': 'Sarah Jenkins',
            'company': 'Apex Media Dynamics',
            'needs': 'Brand identity overhaul, 4K video editing, 3D motion graphics for social launch.',
            'email': 'sarah@apexmedia.com',
            'phone': '+91 98765 43210',
            'address': 'Calicut Cyberpark, Kerala',
        }
        res_post = self.client.post(reverse('client_create'), post_data, follow=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertContains(res_post, "has been added successfully")

        # Verify DB
        client_obj = ClientModel.objects.filter(client_number='CR-CL-001').first()
        self.assertIsNotNone(client_obj)
        self.assertEqual(client_obj.name, 'Sarah Jenkins')
        self.assertEqual(client_obj.company, 'Apex Media Dynamics')
        self.assertEqual(client_obj.needs, 'Brand identity overhaul, 4K video editing, 3D motion graphics for social launch.')
        self.assertEqual(client_obj.department, self.dept_creative)
        self.assertEqual(client_obj.created_by, self.creative_mgr)

        # 3. View Client Detail Dossier
        res_detail = self.client.get(reverse('client_detail', kwargs={'client_id': client_obj.id}))
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, "Apex Media Dynamics")
        self.assertContains(res_detail, "Brand identity overhaul")

        # 4. View in Client Directory
        res_list = self.client.get(reverse('client_list'))
        self.assertEqual(res_list.status_code, 200)
        self.assertContains(res_list, "Apex Media Dynamics")
        self.assertContains(res_list, "CR-CL-001")

    def test_non_creative_manager_cannot_add_client(self):
        """Staff and Non-Creative Managers cannot add clients."""
        # Non-Creative Dept Manager
        self.client.login(username="deptmgr_it", password="password123")
        res_it = self.client.get(reverse('client_create'), follow=True)
        self.assertContains(res_it, "Permission Denied: Only the Creative Department Manager")

        # Creative Staff Member
        self.client.login(username="staff_alex", password="password123")
        res_staff = self.client.get(reverse('client_create'), follow=True)
        self.assertContains(res_staff, "Permission Denied: Only the Creative Department Manager")

    def test_client_sequential_number_generation(self):
        """ClientModel.generate_next_client_number increments sequentially."""
        next_1 = ClientModel.generate_next_client_number("Aider Creative")
        self.assertEqual(next_1, "CR-CL-001")

        ClientModel.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            client_number=next_1,
            name='Acme Client',
            company='Acme Corp',
            needs='Video campaigns'
        )

        next_2 = ClientModel.generate_next_client_number("Aider Creative")
        self.assertEqual(next_2, "CR-CL-002")

    def test_creative_manager_can_edit_and_delete_client(self):
        """Creative Department Manager can update and delete clients."""
        self.client.login(username="deptmgr_rachel", password="password123")

        client_obj = ClientModel.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            client_number='CR-CL-099',
            name='Old Name',
            company='Old Company',
            needs='Old Needs'
        )

        # Edit Client
        edit_data = {
            'client_number': 'CR-CL-099',
            'name': 'Updated Client Name',
            'company': 'Updated Enterprise',
            'needs': 'Updated Creative Scope and Deliverables',
        }
        res_edit = self.client.post(reverse('client_edit', kwargs={'client_id': client_obj.id}), edit_data, follow=True)
        self.assertEqual(res_edit.status_code, 200)

        client_obj.refresh_from_db()
        self.assertEqual(client_obj.name, 'Updated Client Name')
        self.assertEqual(client_obj.company, 'Updated Enterprise')
        self.assertEqual(client_obj.needs, 'Updated Creative Scope and Deliverables')

        # Delete Client
        res_del = self.client.post(reverse('client_delete', kwargs={'client_id': client_obj.id}), follow=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(ClientModel.objects.filter(id=client_obj.id).exists())

    def test_creative_members_can_view_clients_but_cannot_add_clients(self):
        """Every creative department member can view clients and details, but only manager can add/assign."""
        client_obj = ClientModel.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            client_number='CR-CL-101',
            name='Global Brand Rep',
            company='Brand Innovators Inc',
            needs='Marketing strategy, 3D character design, corporate documentary editing.'
        )

        # 1. Executive can view directory and details, but cannot add
        self.client.login(username="staff_daniel", password="password123")
        res_list = self.client.get(reverse('client_list'))
        self.assertEqual(res_list.status_code, 200)
        self.assertContains(res_list, "Brand Innovators Inc")

        res_detail = self.client.get(reverse('client_detail', kwargs={'client_id': client_obj.id}))
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, "Brand Innovators Inc")

        res_add = self.client.get(reverse('client_create'), follow=True)
        self.assertContains(res_add, "Permission Denied: Only the Creative Department Manager")

        # 2. Staff member can view directory and details, but cannot add
        self.client.login(username="staff_liam", password="password123")
        res_staff_list = self.client.get(reverse('client_list'))
        self.assertEqual(res_staff_list.status_code, 200)
        self.assertContains(res_staff_list, "Brand Innovators Inc")

        res_staff_detail = self.client.get(reverse('client_detail', kwargs={'client_id': client_obj.id}))
        self.assertEqual(res_staff_detail.status_code, 200)
        self.assertContains(res_staff_detail, "Brand Innovators Inc")

        res_staff_add = self.client.get(reverse('client_create'), follow=True)
        self.assertContains(res_staff_add, "Permission Denied: Only the Creative Department Manager")

        # 3. Intern can view directory and details, but cannot add
        self.client.login(username="intern_sam", password="password123")
        res_intern_list = self.client.get(reverse('client_list'))
        self.assertEqual(res_intern_list.status_code, 200)
        self.assertContains(res_intern_list, "Brand Innovators Inc")

        res_intern_add = self.client.get(reverse('client_create'), follow=True)
        self.assertContains(res_intern_add, "Permission Denied: Only the Creative Department Manager")

    def test_creative_manager_can_assign_client_to_multiple_branches_and_executives(self):
        """
        Creative Department Manager can assign a client to multiple branches for different tasks.
        e.g., Designing branch (Executive Daniel) and Editing branch (Executive Eric).
        """
        self.client.login(username="deptmgr_rachel", password="password123")

        client_obj = ClientModel.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            client_number='CR-CL-200',
            name='Elena Rostova',
            company='Starlight Entertainment',
            needs='Poster designing and 4K trailer video editing.'
        )

        # 1. Assign to Designing branch & Executive Daniel for Poster Designing
        res_assign_1 = self.client.post(
            reverse('client_assign', kwargs={'client_id': client_obj.id}),
            {
                'client': client_obj.id,
                'branch': self.branch_design.id,
                'executive': self.creative_staff_daniel.id,
                'task_title': 'Cinema Poster & Visual Identity',
                'task_scope': 'Design main movie poster in portrait and landscape key art.',
                'deadline': (timezone.now() + datetime.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),
            },
            follow=True
        )
        self.assertEqual(res_assign_1.status_code, 200)

        # 2. Assign same client to Editing branch & Executive Eric for Video Trailer Editing
        res_assign_2 = self.client.post(
            reverse('client_assign', kwargs={'client_id': client_obj.id}),
            {
                'client': client_obj.id,
                'branch': self.branch_edit.id,
                'executive': self.creative_exec_edit.id,
                'task_title': '4K Cinematic Trailer Editing',
                'task_scope': 'Cut 90-second teaser and 2.5-minute theatrical trailer with sound design.',
                'deadline': (timezone.now() + datetime.timedelta(days=10)).strftime('%Y-%m-%dT%H:%M'),
            },
            follow=True
        )
        self.assertEqual(res_assign_2.status_code, 200)

        # Verify DB has 2 distinct branch assignments for this client
        assignments = ClientAssignment.objects.filter(client=client_obj)
        self.assertEqual(assignments.count(), 2)

        design_assign = assignments.get(branch=self.branch_design)
        self.assertEqual(design_assign.executive, self.creative_staff_daniel)
        self.assertEqual(design_assign.task_title, 'Cinema Poster & Visual Identity')
        self.assertEqual(design_assign.status, ClientAssignment.Status.ASSIGNED_TO_EXECUTIVE)

        edit_assign = assignments.get(branch=self.branch_edit)
        self.assertEqual(edit_assign.executive, self.creative_exec_edit)
        self.assertEqual(edit_assign.task_title, '4K Cinematic Trailer Editing')
        self.assertEqual(edit_assign.status, ClientAssignment.Status.ASSIGNED_TO_EXECUTIVE)

    def test_executive_can_delegate_client_task_to_branch_member_or_intern(self):
        """
        Branch Executive receives the client assignment and delegates it to a staff member or intern in their branch.
        """
        client_obj = ClientModel.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            client_number='CR-CL-300',
            name='Marcus Vance',
            company='Vance Tech',
            needs='Product visual guidelines'
        )

        assignment = ClientAssignment.objects.create(
            client=client_obj,
            branch=self.branch_design,
            assigned_by=self.creative_mgr,
            executive=self.creative_staff_daniel,
            task_title='Product 3D Icons Design',
            task_scope='Create 12 vectorized 3D app icons.',
            status=ClientAssignment.Status.ASSIGNED_TO_EXECUTIVE
        )

        # Executive Daniel logs in and views allocations portal
        self.client.login(username="staff_daniel", password="password123")

        portal_res = self.client.get(reverse('executive_client_assignments'))
        self.assertEqual(portal_res.status_code, 200)
        self.assertContains(portal_res, "Product 3D Icons Design")
        self.assertContains(portal_res, "Vance Tech")

        # Executive delegates task to intern Sam
        del_post = self.client.post(
            reverse('executive_client_delegate', kwargs={'assignment_id': assignment.id}),
            {
                'delegated_member': self.creative_intern_sam.id,
                'executive_notes': 'Please follow Figma 2026 design token guidelines.',
                'deadline': (timezone.now() + datetime.timedelta(days=5)).strftime('%Y-%m-%dT%H:%M'),
            },
            follow=True
        )
        self.assertEqual(del_post.status_code, 200)

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ClientAssignment.Status.DELEGATED)
        self.assertEqual(assignment.delegated_member, self.creative_intern_sam)
        self.assertEqual(assignment.executive_notes, 'Please follow Figma 2026 design token guidelines.')

    def test_branch_member_sees_delegated_client_tasks_in_dashboard(self):
        """
        Intern / Staff member sees the client task delegated to them by their branch executive on dashboard.
        """
        client_obj = ClientModel.objects.create(
            department=self.dept_creative,
            created_by=self.creative_mgr,
            client_number='CR-CL-400',
            name='Sofia Bennett',
            company='Horizon Ventures',
            needs='Social media visual campaign'
        )

        assignment = ClientAssignment.objects.create(
            client=client_obj,
            branch=self.branch_design,
            assigned_by=self.creative_mgr,
            executive=self.creative_staff_daniel,
            delegated_member=self.creative_intern_sam,
            delegated_at=timezone.now(),
            task_title='Social Banner Suite',
            task_scope='Produce 10 Instagram story templates in 1080x1920 format.',
            executive_notes='Use brand colors #4f46e5 and #06b6d4.',
            status=ClientAssignment.Status.DELEGATED
        )

        # Intern Sam logs into employee dashboard
        self.client.login(username="intern_sam", password="password123")
        dash_res = self.client.get(reverse('employee_dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, "Social Banner Suite")
        self.assertContains(dash_res, "Horizon Ventures")
        self.assertContains(dash_res, "Use brand colors #4f46e5")

    def test_branch_executives_api(self):
        """branch_executives_api returns executives in requested branch."""
        self.client.login(username="deptmgr_rachel", password="password123")
        res = self.client.get(reverse('branch_executives_api', kwargs={'branch_id': self.branch_design.id}))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('executives', data)
        self.assertTrue(any(e['id'] == self.creative_staff_daniel.id for e in data['executives']))


