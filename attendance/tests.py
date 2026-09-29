from datetime import timedelta

from django.test import TestCase, Client
from django.urls import resolve
from django.contrib.sessions.models import Session
from django.utils import timezone
import numpy as np

from core.models import Utilisateur
from attendance.utils.face_utils import _assign_faces_to_students


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


class MultiFaceMatchingTest(TestCase):
    def test_two_faces_can_match_two_different_students_in_one_frame(self):
        class StudentEmbedding:
            def __init__(self, student_id, embedding):
                self.pk = student_id
                self.embedding = embedding

            def get_embedding(self):
                return self.embedding

        first_student = StudentEmbedding(1, np.array([1.0, 0.0], dtype=np.float32))
        second_student = StudentEmbedding(2, np.array([0.0, 1.0], dtype=np.float32))
        face_embeddings = [
            np.array([0.99, 0.01], dtype=np.float32),
            np.array([0.01, 0.99], dtype=np.float32),
        ]

        assignments = _assign_faces_to_students(
            face_embeddings,
            [first_student, second_student],
        )

        self.assertEqual(assignments[0].pk, first_student.pk)
        self.assertEqual(assignments[1].pk, second_student.pk)
        self.assertEqual(len({student.pk for student in assignments.values()}), 2)
