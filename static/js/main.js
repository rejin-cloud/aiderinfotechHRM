// HRMS V1 Interactive Frontend Scripts

document.addEventListener('DOMContentLoaded', function () {
    // Dynamic Branch Filtering based on Department Selection in forms
    const deptSelect = document.getElementById('department-select');
    const branchSelect = document.getElementById('branch-select');

    if (deptSelect && branchSelect) {
        deptSelect.addEventListener('change', function () {
            const deptId = this.value;
            branchSelect.innerHTML = '<option value="">---------</option>';
            
            if (!deptId) return;

            fetch(`/api/branches/?department_id=${deptId}`)
                .then(response => response.json())
                .then(data => {
                    data.branches.forEach(branch => {
                        const option = document.createElement('option');
                        option.value = branch.id;
                        option.textContent = branch.name + (branch.location ? ` (${branch.location})` : '');
                        branchSelect.appendChild(option);
                    });
                })
                .catch(err => console.error('Failed to load branches:', err));
        });
    }

    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Auto-dismiss alert messages after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});
