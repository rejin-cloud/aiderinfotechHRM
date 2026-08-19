from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.users.models import User
from apps.departments.models import Department, Branch
from apps.recruitment.models import Candidate


class RecruitmentPipelineTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Design Studio")
        self.branch = Branch.objects.create(name="Calicut Branch", department=self.dept)

        self.hr_user = User.objects.create_user(
            username='hr_officer',
            email='hr@aider.internal',
            password='password123',
            role=User.Role.HR,
            department=self.dept,
            branch=self.branch,
        )

        self.staff_user = User.objects.create_user(
            username='regular_staff',
            email='staff@aider.internal',
            password='password123',
            role=User.Role.STAFF,
            department=self.dept,
            branch=self.branch,
        )

    def test_candidate_creation_workflow(self):
        self.client.force_login(self.hr_user)

        # 1. Create candidate via view
        res = self.client.post(reverse('candidate_create'), {
            'name': 'Rahul Sharma',
            'phone': '+91 9876543210',
            'email': 'rahul.sharma@example.com',
            'place': 'Kochi, Kerala',
            'department': self.dept.id,
            'branch': self.branch.id,
            'role_applied': Candidate.RoleApplied.STAFF,
            'designation_applied': 'Junior Graphic Designer',
            'qualification': 'B.Des in Visual Communication',
            'experience_years': '1 Year',
            'notes': 'Strong Figma and Photoshop portfolio.',
        })
        self.assertEqual(res.status_code, 302)

        cand = Candidate.objects.get(name='Rahul Sharma')
        self.assertEqual(cand.status, Candidate.Status.TO_BE_CALLED)
        self.assertEqual(cand.place, 'Kochi, Kerala')
        self.assertEqual(cand.phone, '+91 9876543210')
        self.assertEqual(cand.created_by, self.hr_user)

    def test_candidate_marking_called_and_approval_flow(self):
        self.client.force_login(self.hr_user)

        cand = Candidate.objects.create(
            name='Ananya Nair',
            phone='+91 9123456789',
            place='Calicut, Kerala',
            department=self.dept,
            branch=self.branch,
            role_applied=Candidate.RoleApplied.EXECUTIVE,
            designation_applied='UI/UX Lead',
            status=Candidate.Status.TO_BE_CALLED,
            created_by=self.hr_user,
        )

        # 1. Log call -> Mark as CALLED
        call_res = self.client.post(reverse('candidate_mark_called', args=[cand.id]), {
            'call_outcome': 'CALLED',
            'call_notes': 'Spoke with candidate. Immediate joiner, expected salary matches budget.',
            'call_rating': 4,
        })
        self.assertEqual(call_res.status_code, 302)

        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.Status.CALLED)
        self.assertEqual(cand.called_by, self.hr_user)
        self.assertIsNotNone(cand.called_at)
        self.assertEqual(cand.call_rating, 4)

        # 2. Decision review -> Approve candidate
        decide_res = self.client.post(reverse('candidate_decide', args=[cand.id]), {
            'decision': 'APPROVED',
            'approval_notes': 'Approved for technical and creative round.',
        })
        self.assertEqual(decide_res.status_code, 302)

        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.Status.APPROVED)
        self.assertEqual(cand.reviewed_by, self.hr_user)

        # 3. Verify candidate appears in Approved Candidates List
        app_list_res = self.client.get(reverse('candidate_approved_list'))
        self.assertEqual(app_list_res.status_code, 200)
        self.assertContains(app_list_res, 'Ananya Nair')
        self.assertContains(app_list_res, '+91 9123456789')
        self.assertContains(app_list_res, 'Calicut, Kerala')
        self.assertContains(app_list_res, 'Design Studio')
        self.assertContains(app_list_res, 'Calicut Branch')

        # 4. Schedule Interview
        interview_date = timezone.localdate() + timezone.timedelta(days=2)
        interview_res = self.client.post(reverse('candidate_schedule_interview', args=[cand.id]), {
            'interview_date': interview_date.strftime('%Y-%m-%d'),
            'interview_time': '11:00:00',
            'interview_mode': 'ONLINE',
            'interview_location': 'https://meet.google.com/abc-defg-hij',
            'interviewer_name': 'Design Director & HR Head',
            'interview_instructions': 'Prepare a 15-minute presentation of recent projects.',
        })
        self.assertEqual(interview_res.status_code, 302)

        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.Status.INTERVIEW_SCHEDULED)
        self.assertEqual(cand.interview_mode, 'ONLINE')
        self.assertEqual(cand.interview_location, 'https://meet.google.com/abc-defg-hij')

        # 5. Verify Candidate Detailed Dossier
        detail_res = self.client.get(reverse('candidate_detail', args=[cand.id]))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, 'Ananya Nair')
        self.assertContains(detail_res, '+91 9123456789')
        self.assertContains(detail_res, 'Calicut, Kerala')
        self.assertContains(detail_res, 'Design Studio')
        self.assertContains(detail_res, 'Interview Arrangement')
        self.assertContains(detail_res, 'meet.google.com')

    def test_rejection_workflow(self):
        self.client.force_login(self.hr_user)

        cand = Candidate.objects.create(
            name='Kiran Kumar',
            phone='+91 9888877777',
            place='Trivandrum',
            status=Candidate.Status.TO_BE_CALLED,
        )

        # Call & directly reject
        call_res = self.client.post(reverse('candidate_mark_called', args=[cand.id]), {
            'call_outcome': 'REJECTED',
            'call_notes': 'Candidate relocated out of state and unavailable.',
            'call_rating': 1,
        })
        self.assertEqual(call_res.status_code, 302)

        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.Status.REJECTED)

        # Candidate Detail page shows Interview Disabled badge and alert
        detail_res = self.client.get(reverse('candidate_detail', args=[cand.id]))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, 'Interview Disabled (Rejected)')
        self.assertContains(detail_res, 'Interview Scheduling Disabled')
        self.assertNotContains(detail_res, 'Arrange Interview</button>')

        # Direct access / POST to schedule interview is blocked & redirects
        sched_res = self.client.post(reverse('candidate_schedule_interview', args=[cand.id]), {
            'interview_date': '2026-08-25',
            'interview_time': '10:00:00',
            'interview_mode': 'OFFICE',
        })
        self.assertEqual(sched_res.status_code, 302)
        self.assertRedirects(sched_res, reverse('candidate_detail', args=[cand.id]))
        cand.refresh_from_db()
        self.assertEqual(cand.status, Candidate.Status.REJECTED)
        self.assertIsNone(cand.interview_date)

    def test_unauthorized_staff_cannot_access_recruitment(self):
        self.client.force_login(self.staff_user)
        res = self.client.get(reverse('candidate_list'))
        self.assertRedirects(res, reverse('dashboard_router'), target_status_code=302)
