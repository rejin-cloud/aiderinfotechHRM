import datetime
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.departments.models import Branch, Department
from apps.tasks.models import (
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

        # 6. Outside Staff
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
