from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.dashboards.urls')),
    path('', include('apps.users.urls')),
    path('', include('apps.departments.urls')),
    path('', include('apps.reports.urls')),
    path('attendance/', include('apps.attendance.urls')),
    path('tasks/', include('apps.tasks.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
