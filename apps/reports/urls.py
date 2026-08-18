from django.urls import path
from apps.reports import views

urlpatterns = [
    path('reports/', views.reports_hub_view, name='reports_hub'),
    path('reports/export/excel/', views.export_excel_view, name='export_excel'),
    path('reports/export/pdf/', views.export_pdf_view, name='export_pdf'),
    path('reports/export/dossier/<int:user_id>/', views.export_dossier_pdf_view, name='export_dossier_user'),
    path('reports/export/my-dossier/', views.export_dossier_pdf_view, name='export_my_dossier'),
]
