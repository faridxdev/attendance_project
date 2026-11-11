from datetime import timedelta

from django.test import TestCase, Client
from django.urls import resolve
from django.contrib.sessions.models import Session
from django.utils import timezone
import numpy as np

from attendance import views as attendance_views
from attendance.models import Annee, Etudiant, Filiere, Groupe, Matiere, Presence
from core.models import Utilisateur
from attendance.utils.face_utils import _assign_faces_to_students, _students_for_matiere


class UserRoleDisplayTest(TestCase):
    def test_instructor_role_uses_teacher_label_without_changing_role_value(self):
        user = Utilisateur(
            username='enseignant_test',
            nom='Enseignant',
            prenom='Test',
            email='enseignant_test@example.com',
            role='instructeur',
        )

        self.assertEqual(user.get_role_display(), 'Enseignant')
        self.assertEqual(user.role, 'instructeur')


class ResponsableDashboardMetricsTest(TestCase):
    def test_metrics_only_include_responsible_filieres_and_unique_students(self):
        responsable = Utilisateur.objects.create_user(
            username='responsable_test',
            email='responsable_test@example.com',
            password='StrongPass123!',
            nom='Responsable',
            prenom='Test',
            role='responsable_filiere',
        )
        filiere = Filiere.objects.create(
            nom='Informatique',
            code='INFO',
            type_filiere='licence',
            duree=3,
        )
        autre_filiere = Filiere.objects.create(
            nom='Gestion',
            code='GEST',
            type_filiere='licence',
            duree=3,
        )
        responsable.filieres.add(filiere)
        today = timezone.now().date()
        annee = Annee.objects.create(
            filiere=filiere,
            numero=1,
            annee_academique='2025-2026',
            date_debut=today,
            date_fin=today + timedelta(days=180),
        )
        autre_annee = Annee.objects.create(
            filiere=autre_filiere,
            numero=1,
            annee_academique='2025-2026',
            date_debut=today,
            date_fin=today + timedelta(days=180),
        )
        etudiant_present = Etudiant.objects.create(
            matricule='INFO1-001',
            nom='Etudiant',
            prenom='Present',
            date_naissance=today - timedelta(days=7000),
            filiere=filiere,
            annee=annee,
        )
        etudiant_absent = Etudiant.objects.create(
            matricule='INFO1-002',
            nom='Etudiant',
            prenom='Absent',
            date_naissance=today - timedelta(days=7000),
            filiere=filiere,
            annee=annee,
        )
        etudiant_autre_filiere = Etudiant.objects.create(
            matricule='GEST1-001',
            nom='Etudiant',
            prenom='Autre',
            date_naissance=today - timedelta(days=7000),
            filiere=autre_filiere,
            annee=autre_annee,
        )
        matiere_a = Matiere.objects.create(nom='Maths', code='MATH1', annee=annee)
        matiere_b = Matiere.objects.create(nom='Algorithmique', code='INFO1', annee=annee)
        Presence.objects.create(
            etudiant=etudiant_present,
            annee=annee,
            matiere=matiere_a,
            date=today,
            statut='présent',
        )
        Presence.objects.create(
            etudiant=etudiant_present,
            annee=annee,
            matiere=matiere_b,
            date=today,
            statut='présent',
        )
        Presence.objects.create(
            etudiant=etudiant_absent,
            annee=annee,
            matiere=matiere_a,
            date=today,
            statut='absent',
        )
        Presence.objects.create(
            etudiant=etudiant_autre_filiere,
            annee=autre_annee,
            date=today,
            statut='présent',
        )

        client = Client()
        client.force_login(responsable)
        response = client.get('/dashboard/responsable/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_etudiants'], 2)
        self.assertEqual(response.context['presents_today'], 1)
        self.assertEqual(response.context['taux_presence'], 66.7)

        report_response = client.get(
            '/rapports/',
            {'type': 'journalier'},
        )
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.context['stats']['total'], 3)
        self.assertEqual(report_response.context['stats']['presents'], 2)
        self.assertEqual(report_response.context['stats']['taux'], 66.7)


class FinalizePointageTest(TestCase):
    def setUp(self):
        self.instructeur = Utilisateur.objects.create_user(
            username='instructeur_test',
            email='instructeur_test@example.com',
            password='StrongPass123!',
            nom='Instructeur',
            prenom='Test',
            role='instructeur',
        )
        self.responsable = Utilisateur.objects.create_user(
            username='responsable_pointage_test',
            email='responsable_pointage_test@example.com',
            password='StrongPass123!',
            nom='Responsable',
            prenom='Test',
            role='responsable_filiere',
        )
        self.filiere = Filiere.objects.create(
            nom='Informatique',
            code='INFO',
            type_filiere='licence',
            duree=3,
        )
        today = timezone.localdate()
        self.annee = Annee.objects.create(
            filiere=self.filiere,
            numero=1,
            annee_academique='2025-2026',
            date_debut=today,
            date_fin=today + timedelta(days=180),
        )
        self.groupe = Groupe.objects.create(
            annee=self.annee,
            nom='Groupe 1',
            code='INFO-G1',
        )
        autre_groupe = Groupe.objects.create(
            annee=self.annee,
            nom='Groupe 2',
            code='INFO-G2',
        )
        self.matiere = Matiere.objects.create(
            nom='Mathématiques',
            code='MATH1',
            annee=self.annee,
            groupe=self.groupe,
            instructeur=self.instructeur,
        )
        self.matiere.filieres.add(self.filiere)
        self.responsable.filieres.add(self.filiere)
        self.etudiant_present = self._create_student(
            'INFO1-001',
            'Présent',
            self.groupe,
        )
        self.etudiant_absent = self._create_student(
            'INFO1-002',
            'Absent',
            self.groupe,
        )
        self.etudiant_autre_groupe = self._create_student(
            'INFO1-003',
            'Autre groupe',
            autre_groupe,
        )
        self.etudiant_inactif = self._create_student(
            'INFO1-004',
            'Inactif',
            self.groupe,
        )
        self.etudiant_inactif.actif = False
        self.etudiant_inactif.save(update_fields=['actif'])
        self.client = Client()
        self.client.force_login(self.instructeur)

    def tearDown(self):
        with attendance_views.pointage_lock:
            attendance_views.pointage_actif = False
            attendance_views.pointage_matiere_id = None

    def _create_student(self, matricule, prenom, groupe):
        today = timezone.localdate()
        return Etudiant.objects.create(
            matricule=matricule,
            nom='Etudiant',
            prenom=prenom,
            date_naissance=today - timedelta(days=7000),
            filiere=self.filiere,
            annee=self.annee,
            groupe=groupe,
            embedding=b'test-embedding',
        )

    def test_scan_roster_is_limited_to_subject_year_and_group(self):
        roster_ids = set(
            _students_for_matiere(self.matiere).values_list('pk', flat=True)
        )

        self.assertEqual(
            roster_ids,
            {self.etudiant_present.pk, self.etudiant_absent.pk},
        )

    def test_stopping_pointage_records_absence_and_report_rate(self):
        today = timezone.localdate()
        Presence.objects.create(
            etudiant=self.etudiant_present,
            annee=self.annee,
            groupe=self.groupe,
            matiere=self.matiere,
            date=today,
            statut='présent',
        )

        cancelled_start = self.client.post(
            '/start_pointage/',
            {'matiere_id': self.matiere.pk},
        )
        self.assertEqual(cancelled_start.status_code, 200)
        cancelled_stop = self.client.post('/stop_pointage/', {'cancel': 'true'})
        self.assertEqual(cancelled_stop.status_code, 200)
        self.assertFalse(
            Presence.objects.filter(
                etudiant=self.etudiant_absent,
                matiere=self.matiere,
                date=today,
            ).exists()
        )

        start_response = self.client.post(
            '/start_pointage/',
            {'matiere_id': self.matiere.pk},
        )
        self.assertEqual(start_response.status_code, 200)

        stop_response = self.client.post('/stop_pointage/')

        self.assertEqual(stop_response.status_code, 200)
        self.assertEqual(stop_response.json()['absences_created'], 1)
        self.assertEqual(
            Presence.objects.get(
                etudiant=self.etudiant_absent,
                matiere=self.matiere,
                date=today,
            ).statut,
            'absent',
        )
        self.assertFalse(
            Presence.objects.filter(
                etudiant=self.etudiant_autre_groupe,
                matiere=self.matiere,
                date=today,
            ).exists()
        )
        self.assertFalse(
            Presence.objects.filter(
                etudiant=self.etudiant_inactif,
                matiere=self.matiere,
                date=today,
            ).exists()
        )

        repeated_stop = self.client.post('/stop_pointage/')
        self.assertEqual(repeated_stop.status_code, 200)
        self.assertEqual(repeated_stop.json()['absences_created'], 0)
        self.assertEqual(
            Presence.objects.filter(
                etudiant=self.etudiant_absent,
                matiere=self.matiere,
                date=today,
            ).count(),
            1,
        )

        self.client.force_login(self.responsable)
        dashboard_response = self.client.get('/dashboard/responsable/')
        self.assertEqual(dashboard_response.context['taux_presence'], 50.0)

        report_response = self.client.get(
            '/rapports/',
            {
                'type': 'journalier',
                'matiere': self.matiere.pk,
            },
        )
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.context['stats']['total'], 2)
        self.assertEqual(report_response.context['stats']['presents'], 1)
        self.assertEqual(report_response.context['stats']['taux'], 50.0)


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
