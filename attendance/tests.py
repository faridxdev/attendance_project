from datetime import timedelta

from django.test import TestCase, Client
from django.urls import resolve
from django.contrib.sessions.models import Session
from django.utils import timezone

from core.models import Utilisateur


class MaintenanceAdminRoutesTest(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_user(
            username='admin_test',
            email='admin_test@example.com',
            password='StrongPass123!',
            nom='Admin',
            prenom='Test',
            role='administrateur',
        )

    def test_maintenance_routes_resolve_to_attendance_views(self):
        route = resolve('/admin/backup/')
        self.assertEqual(route.view_name, 'attendance:backup_database')

        route = resolve('/admin/check-integrity/')
        self.assertEqual(route.view_name, 'attendance:check_integrity')

        route = resolve('/admin/system-update/')
        self.assertEqual(route.view_name, 'attendance:system_update')

    def test_admin_can_call_maintenance_endpoint(self):
        client = Client()
        client.force_login(self.admin)

        response = client.post('/admin/backup/')
        self.assertNotEqual(response.status_code, 403)

    def test_admin_dashboard_metrics_are_dynamic(self):
        client = Client()
        client.force_login(self.admin)
        Session.objects.create(
            session_key='dynamic-session-test',
            session_data='{}',
            expire_date=timezone.now() + timedelta(days=1),
        )

        response = client.get('/dashboard/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('active_sessions', response.context)
        self.assertIn('performance_score', response.context)
        self.assertIn('security_status', response.context)
        self.assertEqual(response.context['active_sessions'], Session.objects.filter(expire_date__gt=timezone.now()).count())
        self.assertNotEqual(response.context['performance_score'], '95%')
