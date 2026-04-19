from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    # Authentification
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Enrôlement
    path('enroller/', views.enroller_view, name='enroller'),
    path('capture/', views.capture_photo, name='capture'),

    # Flux et contrôle pointage
    path('video_feed/', views.video_feed, name='video_feed'),
    path('start_pointage/', views.start_pointage, name='start_pointage'),
    path('stop_pointage/', views.stop_pointage, name='stop_pointage'),

    # Dashboard unique (redirection) + spécifiques
    path('dashboard/', views.dashboard_redirect, name='dashboard'),
    path('dashboard/instructeur/', views.dashboard_instructeur, name='dashboard_instructeur'),
    path('dashboard/responsable/', views.dashboard_responsable, name='dashboard_responsable'),
    path('dashboard/admin/', views.dashboard_admin, name='dashboard_admin'),
    path('rapports/', views.rapports_view, name='rapports'),

    # Outils d'administration
    path('admin/backup/', views.backup_database, name='backup_database'),
    path('admin/clean-logs/', views.clean_logs, name='clean_logs'),
    path('admin/check-integrity/', views.check_integrity, name='check_integrity'),
    path('admin/system-update/', views.system_update, name='system_update'),
    path('admin/restart-services/', views.restart_services, name='restart_services'),
]