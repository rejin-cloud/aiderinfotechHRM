from django.test import TestCase
from apps.users.models import User
from apps.departments.models import Department, Branch
from apps.hierarchy.permissions import can_create_department, can_create_branch, can_assign_role, can_manage_user

class RBACUserModelTest(TestCase):
    def setUp(self):
        self.dept_aider = Department.objects.create(name="Aider Creative")
        self.branch_design = Branch.objects.create(department=self.dept_aider, name="Designing")

        self.superadmin = User.objects.create_user(
            username="superadmin",
            role=User.Role.SUPERADMIN
        )
        self.hr = User.objects.create_user(
            username="hr_user",
            role=User.Role.HR,
            department=self.dept_aider
        )
        self.manager = User.objects.create_user(
            username="mgr_user",
            role=User.Role.MANAGER,
            department=self.dept_aider
        )
        self.dept_mgr = User.objects.create_user(
            username="deptmgr_user",
            role=User.Role.DEPT_MANAGER,
            department=self.dept_aider,
            branch=self.branch_design
        )
        self.staff = User.objects.create_user(
            username="staff_user",
            role=User.Role.STAFF,
            department=self.dept_aider,
            branch=self.branch_design
        )

    def test_system_levels(self):
        self.assertEqual(self.superadmin.level, 1)
        self.assertEqual(self.hr.level, 2)
        self.assertEqual(self.manager.level, 2)
        self.assertEqual(self.dept_mgr.level, 3)
        self.assertEqual(self.staff.level, 4)

    def test_department_creation_permissions(self):
        self.assertTrue(can_create_department(self.superadmin))
        self.assertFalse(can_create_department(self.hr))
        self.assertFalse(can_create_department(self.manager))
        self.assertFalse(can_create_department(self.dept_mgr))
        self.assertFalse(can_create_department(self.staff))

    def test_branch_creation_permissions(self):
        self.assertTrue(can_create_branch(self.superadmin))
        self.assertTrue(can_create_branch(self.manager))  # Manager has dedicated branch creation
        self.assertFalse(can_create_branch(self.hr))
        self.assertFalse(can_create_branch(self.dept_mgr))
        self.assertFalse(can_create_branch(self.staff))

    def test_role_assignment_boundaries(self):
        # Superadmin can assign HR, Manager, etc.
        self.assertTrue(can_assign_role(self.superadmin, User.Role.HR))
        self.assertTrue(can_assign_role(self.superadmin, User.Role.MANAGER))

        # HR and Manager can assign Dept Managers, Execs, Interns, Staff
        self.assertTrue(can_assign_role(self.hr, User.Role.DEPT_MANAGER))
        self.assertTrue(can_assign_role(self.manager, User.Role.DEPT_MANAGER))
        self.assertFalse(can_assign_role(self.hr, User.Role.SUPERADMIN))
        self.assertFalse(can_assign_role(self.manager, User.Role.SUPERADMIN))

        # Dept Manager can only assign Exec, Intern, Staff
        self.assertTrue(can_assign_role(self.dept_mgr, User.Role.EXECUTIVE))
        self.assertTrue(can_assign_role(self.dept_mgr, User.Role.STAFF))
        self.assertFalse(can_assign_role(self.dept_mgr, User.Role.DEPT_MANAGER))

        # Staff has no assignment capability
        self.assertFalse(can_assign_role(self.staff, User.Role.STAFF))
