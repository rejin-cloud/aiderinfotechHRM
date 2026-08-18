import datetime
from django.core.management.base import BaseCommand
from apps.users.models import User
from apps.departments.models import Department, Branch

class Command(BaseCommand):
    help = 'Seeds initial corporate departments, default branches, and test role accounts per HRMS V1 Blueprint'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Beginning HRMS V1 database seed provisioning...'))

        # -------------------------------------------------------------
        # 1. Provision Corporate Departments & Branches
        # -------------------------------------------------------------
        dept_data = [
            {
                'name': 'Aider Creative',
                'description': 'Creative direction, marketing campaigns, digital design, and media editing hub.',
                'branches': [
                    {'name': 'Marketing', 'location': 'Floor 3, Creative Block'},
                    {'name': 'Designing', 'location': 'Studio A, Creative Block'},
                    {'name': 'Editing', 'location': 'Studio B, Media Wing'},
                ]
            },
            {
                'name': 'Aider Academy',
                'description': 'Educational programs, mentorship curricula, and skill acceleration academy.',
                'branches': []  # None (Default core level)
            },
            {
                'name': 'IT Club',
                'description': 'Engineering, cloud infrastructure, software development, and technical club operations.',
                'branches': [
                    {'name': 'IT Club Balussery', 'location': 'Balussery Innovation Center'},
                    {'name': 'IT Club Calicut', 'location': 'Calicut Technology Park'},
                ]
            },
        ]

        created_departments = {}
        created_branches = {}

        for d_info in dept_data:
            dept, created = Department.objects.get_or_create(
                name=d_info['name'],
                defaults={'description': d_info['description']}
            )
            created_departments[dept.name] = dept
            status_text = 'Created' if created else 'Existing'
            self.stdout.write(f"  [+] Department: {dept.name} ({status_text})")

            for b_info in d_info['branches']:
                branch, b_created = Branch.objects.get_or_create(
                    department=dept,
                    name=b_info['name'],
                    defaults={'location': b_info['location']}
                )
                created_branches[f"{dept.name}:{branch.name}"] = branch
                b_status = 'Created' if b_created else 'Existing'
                self.stdout.write(f"      - Branch: {branch.name} ({b_status})")

        # -------------------------------------------------------------
        # 2. Provision Multi-Role Test Accounts
        # -------------------------------------------------------------
        users_seed = [
            {
                'username': 'superadmin',
                'first_name': 'Alexander',
                'last_name': 'Vance',
                'email': 'superadmin@aider.internal',
                'role': User.Role.SUPERADMIN,
                'department': None,
                'branch': None,
                'employee_id': 'EMP-0001',
                'designation': 'Chief Executive Officer / System Owner',
                'is_superuser': True,
                'is_staff': True,
                'avatar_color': '#dc2626',
            },
            {
                'username': 'serveradmin',
                'first_name': 'Marcus',
                'last_name': 'Sterling',
                'email': 'sysadmin@aider.internal',
                'role': User.Role.SERVER_ADMIN,
                'department': created_departments.get('IT Club'),
                'branch': None,
                'employee_id': 'EMP-0002',
                'designation': 'Principal Server Architect',
                'is_superuser': True,
                'is_staff': True,
                'avatar_color': '#0f172a',
            },
            {
                'username': 'hr_sarah',
                'first_name': 'Sarah',
                'last_name': 'Jenkins',
                'email': 'sarah.hr@aider.internal',
                'role': User.Role.HR,
                'department': created_departments.get('Aider Creative'),
                'branch': None,
                'employee_id': 'EMP-0010',
                'designation': 'Head of People & Culture',
                'is_superuser': False,
                'is_staff': True,
                'avatar_color': '#2563eb',
            },
            {
                'username': 'manager_alex',
                'first_name': 'Alex',
                'last_name': 'Morgan',
                'email': 'alex.mgr@aider.internal',
                'role': User.Role.MANAGER,
                'department': created_departments.get('IT Club'),
                'branch': None,
                'employee_id': 'EMP-0020',
                'designation': 'Operations & Branch General Manager',
                'is_superuser': False,
                'is_staff': True,
                'avatar_color': '#0284c7',
            },
            {
                'username': 'deptmgr_rachel',
                'first_name': 'Rachel',
                'last_name': 'Green',
                'email': 'rachel.dept@aider.internal',
                'role': User.Role.DEPT_MANAGER,
                'department': created_departments.get('Aider Creative'),
                'branch': created_branches.get('Aider Creative:Designing'),
                'employee_id': 'EMP-0035',
                'designation': 'Lead Design Department Manager',
                'is_superuser': False,
                'is_staff': False,
                'avatar_color': '#16a34a',
            },
            {
                'username': 'exec_daniel',
                'first_name': 'Daniel',
                'last_name': 'Craig',
                'email': 'daniel.exec@aider.internal',
                'role': User.Role.EXECUTIVE,
                'department': created_departments.get('Aider Creative'),
                'branch': created_branches.get('Aider Creative:Designing'),
                'employee_id': 'EMP-0102',
                'designation': 'Senior UX & Brand Executive',
                'is_superuser': False,
                'is_staff': False,
                'avatar_color': '#ca8a04',
            },
            {
                'username': 'intern_maya',
                'first_name': 'Maya',
                'last_name': 'Lin',
                'email': 'maya.intern@aider.internal',
                'role': User.Role.INTERN,
                'department': created_departments.get('IT Club'),
                'branch': created_branches.get('IT Club:IT Club Calicut'),
                'employee_id': 'EMP-0215',
                'designation': 'Junior Backend Engineering Intern',
                'is_superuser': False,
                'is_staff': False,
                'avatar_color': '#7c3aed',
            },
            {
                'username': 'staff_john',
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'john.staff@aider.internal',
                'role': User.Role.STAFF,
                'department': created_departments.get('Aider Academy'),
                'branch': None,
                'employee_id': 'EMP-0330',
                'designation': 'Academic Operations Staff',
                'is_superuser': False,
                'is_staff': False,
                'avatar_color': '#475569',
            },
        ]

        default_pwd = 'admin123'

        for u_data in users_seed:
            uname = u_data['username']
            user, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'first_name': u_data['first_name'],
                    'last_name': u_data['last_name'],
                    'email': u_data['email'],
                    'role': u_data['role'],
                    'department': u_data['department'],
                    'branch': u_data['branch'],
                    'employee_id': u_data['employee_id'],
                    'designation': u_data['designation'],
                    'is_superuser': u_data['is_superuser'],
                    'is_staff': u_data['is_staff'],
                    'avatar_color': u_data['avatar_color'],
                    'joining_date': datetime.date(2025, 1, 15),
                }
            )
            user.set_password(default_pwd)
            user.role = u_data['role']
            user.department = u_data['department']
            user.branch = u_data['branch']
            user.employee_id = u_data['employee_id']
            user.designation = u_data['designation']
            user.save()

            status = 'Created' if created else 'Updated'
            self.stdout.write(f"  [+] User '{uname}' ({user.get_role_display()} - Level {user.level}) [{status}]")

        self.stdout.write(self.style.SUCCESS('\nHRMS V1 database seed provisioning completed successfully!'))
        self.stdout.write(self.style.SUCCESS('Default password for all demo accounts: admin123'))
