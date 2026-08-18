from django.db import models

class Department(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        return self.users.count()

    @property
    def branch_count(self):
        return self.branches.count()

    @property
    def managers(self):
        return self.users.filter(role__in=['MANAGER', 'DEPT_MANAGER'])


class Branch(models.Model):
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='branches',
        db_index=True
    )
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('department', 'name')
        ordering = ['department__name', 'name']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return f"{self.department.name} - {self.name}"

    @property
    def member_count(self):
        return self.users.count()
