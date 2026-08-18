# Aider Infotech Enterprise Platform

> **Technical Architecture Specification & System Blueprint Implementation**  
> Built with Django 5.x / 6.x, PostgreSQL/SQLite, DRF, ReportLab PDF Engine, pandas/openpyxl Excel Engine, and modern Bootstrap 5 UI.

---

## 1. Architecture & Modular Directory Layout

```
hrms_project/
├── apps/
│   ├── users/            # Custom User model, auth workflows, self-registration, RBAC
│   ├── departments/      # Department & Branch management models/views
│   ├── hierarchy/        # Role permissions, access control decorators, RBAC rules
│   ├── dashboards/       # Multi-role dashboard views & employee workspace
│   ├── attendance/       # Daily attendance, 9:30 AM IST cutoff, multi-stage leaves, monthly matrices
│   └── reports/          # Excel (pandas/openpyxl) & PDF (ReportLab) document tools
├── config/               # Settings (IST Timezone), WSGI/ASGI, Celery configs, URLs
├── templates/            # Shared Bootstrap 5 layouts, dashboards, departments, users, attendance, reports
├── static/               # Static CSS, vector SVG logo & branding, Vanilla JS
├── manage.py
└── db.sqlite3            # SQLite database with test schema
```

---

## 2. Organizational Hierarchy & RBAC Matrix

| Role Name | System Level | Assignment Authority | Dept Creation | Branch Creation | Key Dashboard Focus |
| :--- | :---: | :--- | :---: | :---: | :--- |
| **Superadmin / Owner** | Level 1 | Assigns HR & Managers | **YES** | **YES** | Global System, Dept & Branch Hub, Full User Governance |
| **Server Admin** | Level 1 | Identical to Superadmin | **YES** | **YES** | System Health, Audit Logs, Complete Admin Access |
| **HR** | Level 2 | Assigns Dept Managers (with Manager) | **NO** | **NO** | Employee Directory, Onboarding, HR Reports, Records |
| **Manager** | Level 2 | Assigns Dept Managers (with HR) | **NO** | **YES** | Dedicated Branch Creation Dashboard, Department Analytics |
| **Department Manager**| Level 3 | Manages Executives, Interns, Staff | **NO** | **NO** | Department Roster, Subordinate Management & Approvals |
| **Executive / Intern / Staff** | Level 4 | Self-service only | **NO** | **NO** | Personal Profile, Team Directory, Requests & Announcements |

---

## 3. Pre-Provisioned Seed Data & Demo Accounts

### Default Corporate Topology
- **Aider Creative**: Branches `Marketing`, `Designing`, `Editing`
- **Aider Academy**: None (Default core level)
- **IT Club**: Branches `IT Club Balussery`, `IT Club Calicut`

### Pre-Configured Demo Accounts (Password: `admin123`)

| Username | Role | Level | Department / Branch |
| :--- | :--- | :---: | :--- |
| `superadmin` | Superadmin / Owner | Level 1 | Headquarters |
| `serveradmin` | Server Admin | Level 1 | IT Club |
| `hr_sarah` | HR | Level 2 | Aider Creative |
| `manager_alex` | Manager | Level 2 | IT Club |
| `deptmgr_rachel` | Department Manager | Level 3 | Aider Creative (Designing) |
| `exec_daniel` | Executive | Level 4 | Aider Creative (Designing) |
| `intern_maya` | Intern | Level 4 | IT Club (Calicut) |
| `staff_john` | Staff | Level 4 | Aider Academy |

> **Live 1-Click Role Switcher**: A switcher banner is present at the top of the web UI to effortlessly jump between any role during testing.

---

## 4. How to Run & Verify Locally

### 1. Start the Development Server
```bash
python manage.py runserver 127.0.0.1:8000
```
Open your browser at [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

### 2. Re-Seed Database (Optional)
```bash
python manage.py seed_hrms
```

### 3. Run Automated Test Suite
```bash
python manage.py test
```
