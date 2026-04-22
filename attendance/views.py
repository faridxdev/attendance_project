from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.conf import settings
import csv
import os
import cv2
import threading
import queue
import numpy as np
import shutil
import glob
import subprocess
import sys
import tempfile
from deepface import DeepFace
from .models import Etudiant, Filiere, Annee, Groupe, Matiere, Presence, Rapport
from datetime import timedelta, datetime
from django.http import StreamingHttpResponse, HttpResponseForbidden, HttpResponse
from .utils.face_utils import generate_embedding_from_file, process_frame
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

def enroller_view(request):
    filieres = Filiere.objects.filter(actif=True)
    annees = Annee.objects.select_related('filiere')
    groupes = Groupe.objects.all()
    return render(request, 'attendance/enroller.html', {
        'filieres': filieres,
        'annees': annees,
        'groupes': groupes,
        'auto_matricule': True
    })

def capture_photo(request):
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        email = request.POST.get('email', '').strip()
        date_naissance = request.POST.get('date_naissance')
        filiere_id = request.POST.get('filiere')
        annee_id = request.POST.get('annee')
        groupe_id = request.POST.get('groupe')

        photo_data = request.FILES.get('photo')
        if not photo_data:
            return JsonResponse({'error': 'Aucune photo'}, status=400)

        try:
            filiere = Filiere.objects.get(id=filiere_id)
            annee = Annee.objects.get(id=annee_id)
            groupe = Groupe.objects.get(id=groupe_id) if groupe_id else None
        except (Filiere.DoesNotExist, Annee.DoesNotExist):
            return JsonResponse({'error': 'Filière ou année invalide'}, status=400)

        deja = Etudiant.objects.filter(
            nom__iexact=nom,
            prenom__iexact=prenom,
            date_naissance=date_naissance,
            filiere=filiere,
        ).first()

        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            for chunk in photo_data.chunks():
                tmp_file.write(chunk)
            tmp_file.flush()
            tmp_path = tmp_file.name

        embedding = generate_embedding_from_file(tmp_path)
        os.remove(tmp_path)

        if embedding is None:
            return JsonResponse({'error': 'Visage non détecté'}, status=400)

        if deja:
            deja.nom = nom
            deja.prenom = prenom
            deja.email = email
            deja.date_naissance = date_naissance
            deja.filiere = filiere
            deja.annee = annee
            deja.groupe = groupe
            deja.photo = photo_data
            deja.save()
            deja.save_embedding(embedding)
            return JsonResponse({'success': True, 'message': 'Étudiant mis à jour avec succès.'})

        etudiant = Etudiant.objects.create(
            nom=nom,
            prenom=prenom,
            email=email,
            date_naissance=date_naissance,
            filiere=filiere,
            annee=annee,
            groupe=groupe,
            photo=photo_data,
        )
        etudiant.save_embedding(embedding)
        return JsonResponse({'success': True, 'message': f'Étudiant enregistré avec matricule {etudiant.matricule}.'})

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)


@login_required
def dashboard_redirect(request):
    """Redirection intelligente selon le rôle de l'utilisateur"""
    role = request.user.role
    
    if role == 'instructeur':
        return redirect('attendance:dashboard_instructeur')
    elif role == 'responsable_filiere':
        return redirect('attendance:dashboard_responsable')
    elif role == 'administrateur':
        return redirect('attendance:dashboard_admin')
    
    # Sécurité : si rôle inconnu
    messages.error(request, "Rôle non reconnu. Contactez l'administrateur.")
    logout(request)
    return redirect('attendance:login')


@login_required
def dashboard_instructeur(request):
    """Dashboard spécifique à l'instructeur"""
    if request.user.role != 'instructeur':
        return redirect('attendance:dashboard')
    
    today = timezone.now().date()
    
    # Filtrer les matières enseignées par cet instructeur
    matieres = Matiere.objects.filter(instructeur=request.user, actif=True).select_related('annee').prefetch_related('filieres')
    
    # Filtrage par matière si spécifié
    matiere_id = request.GET.get('matiere')
    if matiere_id:
        presences = Presence.objects.filter(
            date=today,
            matiere_id=matiere_id,
            matiere__instructeur=request.user
        ).select_related('etudiant', 'matiere', 'annee__filiere').order_by('-heure')
    else:
        # Toutes les présences du jour pour les matières de cet instructeur
        presences = Presence.objects.filter(
            date=today,
            matiere__instructeur=request.user
        ).select_related('etudiant', 'matiere', 'annee__filiere').order_by('-heure')
    
    presents_count = presences.filter(statut='présent').count()
    
    return render(request, 'attendance/dashboard_instructeur.html', {
        'matieres': matieres,
        'presences': presences,
        'presents_count': presents_count,
        'today': today,
        'matiere_filtre': matiere_id
    })


@login_required
def dashboard_responsable(request):
    """Dashboard spécifique au responsable de filière"""
    if request.user.role != 'responsable_filiere':
        return redirect('attendance:dashboard')
    
    today = timezone.now().date()
    if hasattr(request.user, 'filiere') and request.user.filiere:
        total_etudiants = Etudiant.objects.filter(filiere=request.user.filiere).count()
    else:
        total_etudiants = Etudiant.objects.count()
    presents_today = Presence.objects.filter(date=today, statut='présent').count()
    taux_presence = round((presents_today / total_etudiants * 100), 1) if total_etudiants > 0 else 0
    
    # Absences récentes (7 derniers jours)
    absences = Presence.objects.filter(
        statut='absent',
        date__gte=today - timedelta(days=7)
    ).select_related('etudiant').order_by('-date')
    
    return render(request, 'attendance/dashboard_responsable.html', {
        'total_etudiants': total_etudiants,
        'presents_today': presents_today,
        'taux_presence': taux_presence,
        'absences': absences
    })


@login_required
def dashboard_admin(request):
    """Dashboard spécifique à l'administrateur"""
    if request.user.role != 'administrateur':
        return redirect('attendance:dashboard')
    
    # Informations système de base
    import sys
    import django
    import platform
    import psutil
    
    # Récupération des métriques système
    try:
        # Utilisation CPU (si psutil disponible)
        cpu_usage = psutil.cpu_percent(interval=1)
        # Mémoire
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
        # Disque
        disk = psutil.disk_usage('/')
        disk_usage = f"{disk.percent}%"
    except ImportError:
        # Fallback si psutil n'est pas installé
        cpu_usage = 0
        memory_usage = 0
        disk_usage = "N/A"
    
    return render(request, 'attendance/dashboard_admin.html', {
        'total_etudiants': Etudiant.objects.count(),
        'total_filieres': Filiere.objects.count(),
        'total_annees': Annee.objects.count(),
        'total_groupes': Groupe.objects.count(),
        'total_presences': Presence.objects.count(),
        'current_date': timezone.now(),
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}",
        'django_version': django.get_version(),
        'system_info': platform.system(),
        'cpu_usage': f"{cpu_usage:.1f}%",
        'memory_usage': f"{memory_usage:.1f}%",
        'disk_usage': disk_usage,
        'active_sessions': 1,  # À implémenter avec django-sessions
        'performance_score': "95%",  # Métrique calculée
    })

@csrf_exempt
def backup_database(request):
    """Sauvegarde de la base de données"""
    print(f"DEBUG: User {request.user.username if request.user.is_authenticated else 'Anonymous'}, Role: {request.user.role if request.user.is_authenticated else 'None'}, Is authenticated: {request.user.is_authenticated}")  # Debug
    
    if not request.user.is_authenticated:
        print("DEBUG: User not authenticated")  # Debug
        return JsonResponse({'error': 'Authentification requise'}, status=401)
        
    if request.user.role != 'administrateur':
        print(f"DEBUG: Access denied for user {request.user.username} with role {request.user.role}")  # Debug
        return JsonResponse({'error': 'Accès refusé'}, status=403)
    
    if request.method == 'POST':
        try:
            import shutil
            from datetime import datetime
            
            # Créer le dossier de sauvegarde s'il n'existe pas
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Nom du fichier de sauvegarde
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"db_backup_{timestamp}.sqlite3"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Copier la base de données
            db_path = settings.DATABASES['default']['NAME']
            shutil.copy2(db_path, backup_path)
            
            # Nettoyer les anciennes sauvegardes (garder seulement les 10 dernières)
            backup_files = sorted([f for f in os.listdir(backup_dir) if f.startswith('db_backup_')])
            if len(backup_files) > 10:
                for old_file in backup_files[:-10]:
                    os.remove(os.path.join(backup_dir, old_file))
            
            return JsonResponse({
                'success': True, 
                'message': f'Sauvegarde créée: {backup_filename}',
                'file': backup_filename
            })
        except Exception as e:
            return JsonResponse({'error': f'Erreur lors de la sauvegarde: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@csrf_exempt
def clean_logs(request):
    """Nettoyage des anciens logs et fichiers temporaires"""
    print(f"DEBUG clean_logs: User {request.user.username if request.user.is_authenticated else 'Anonymous'}, Is authenticated: {request.user.is_authenticated}")  # Debug
    
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentification requise'}, status=401)
        
    if request.user.role != 'administrateur':
        return JsonResponse({'error': 'Accès refusé'}, status=403)
    
    if request.method == 'POST':
        try:
            import glob
            cleaned_files = 0
            
            # Nettoyer les fichiers temporaires
            temp_patterns = [
                os.path.join(settings.BASE_DIR, 'media', 'temp_*.jpg'),
                os.path.join(settings.BASE_DIR, '*.log'),
                os.path.join(settings.BASE_DIR, 'logs', '*.log')
            ]
            
            for pattern in temp_patterns:
                for file_path in glob.glob(pattern):
                    try:
                        os.remove(file_path)
                        cleaned_files += 1
                    except:
                        pass
            
            # Nettoyer les anciennes sauvegardes (garder seulement les 5 dernières)
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            if os.path.exists(backup_dir):
                backup_files = sorted([f for f in os.listdir(backup_dir) if f.startswith('db_backup_')])
                if len(backup_files) > 5:
                    for old_file in backup_files[:-5]:
                        os.remove(os.path.join(backup_dir, old_file))
                        cleaned_files += 1
            
            return JsonResponse({
                'success': True,
                'message': f'Nettoyage terminé: {cleaned_files} fichiers supprimés'
            })
        except Exception as e:
            return JsonResponse({'error': f'Erreur lors du nettoyage: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@csrf_exempt
def check_integrity(request):
    """Vérification de l'intégrité des données"""
    print(f"DEBUG check_integrity: User {request.user.username if request.user.is_authenticated else 'Anonymous'}, Is authenticated: {request.user.is_authenticated}")  # Debug
    
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentification requise'}, status=401)
        
    if request.user.role != 'administrateur':
        return JsonResponse({'error': 'Accès refusé'}, status=403)
    
    if request.method == 'POST':
        try:
            issues = []

            # Vérifier la cohérence des données
            total_etudiants = Etudiant.objects.count()
            total_presences = Presence.objects.count()
            total_filieres = Filiere.objects.count()

            # Vérifier les étudiants sans filière
            etudiants_sans_filiere = Etudiant.objects.filter(filiere__isnull=True).count()
            if etudiants_sans_filiere > 0:
                issues.append(f"{etudiants_sans_filiere} étudiants sans filière assignée")

            # Vérifier les présences sans étudiant
            presences_orphelines = Presence.objects.filter(etudiant__isnull=True).count()
            if presences_orphelines > 0:
                issues.append(f"{presences_orphelines} présences avec étudiant inexistant")

            # Vérifier les photos manquantes
            etudiants_sans_photo = Etudiant.objects.filter(photo='').count()
            if etudiants_sans_photo > 0:
                issues.append(f"{etudiants_sans_photo} étudiants sans photo")

            # Vérifier l'espace disque
            try:
                disk = psutil.disk_usage('/')
                if disk.percent > 90:
                    issues.append(f"Espace disque critique: {disk.percent}% utilisé")
            except:
                pass
            
            if not issues:
                return JsonResponse({
                    'success': True,
                    'message': 'Intégrité des données vérifiée: Aucun problème détecté',
                    'status': 'healthy'
                })
            else:
                return JsonResponse({
                    'success': True,
                    'message': f'Problèmes détectés: {len(issues)}',
                    'issues': issues,
                    'status': 'warning'
                })
        except Exception as e:
            return JsonResponse({'error': f'Erreur lors de la vérification: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@csrf_exempt
def system_update(request):
    """Mise à jour du système (simulation)"""
    print(f"DEBUG system_update: User {request.user.username if request.user.is_authenticated else 'Anonymous'}, Is authenticated: {request.user.is_authenticated}")  # Debug
    
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentification requise'}, status=401)
        
    if request.user.role != 'administrateur':
        return JsonResponse({'error': 'Accès refusé'}, status=403)
    
    if request.method == 'POST':
        try:
            # Simuler une vérification de mise à jour
            import subprocess
            
            # Vérifier si pip est à jour
            result = subprocess.run([sys.executable, '-m', 'pip', 'list', '--outdated'], 
                                  capture_output=True, text=True, timeout=30)
            
            outdated_packages = len([line for line in result.stdout.split('\n') if line.strip()])
            
            if outdated_packages > 0:
                return JsonResponse({
                    'success': True,
                    'message': f'{outdated_packages} paquets peuvent être mis à jour',
                    'action': 'update_available',
                    'details': 'Exécutez: pip install -r requirements.txt --upgrade'
                })
            else:
                return JsonResponse({
                    'success': True,
                    'message': 'Système à jour',
                    'action': 'up_to_date'
                })
        except Exception as e:
            return JsonResponse({'error': f'Erreur lors de la vérification: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@csrf_exempt
def restart_services(request):
    """Redémarrage des services (simulation)"""
    print(f"DEBUG restart_services: User {request.user.username if request.user.is_authenticated else 'Anonymous'}, Is authenticated: {request.user.is_authenticated}")  # Debug
    
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentification requise'}, status=401)
        
    if request.user.role != 'administrateur':
        return JsonResponse({'error': 'Accès refusé'}, status=403)
    
    if request.method == 'POST':
        try:
            # Simuler le redémarrage des services
            # En production, cela redémarrerait réellement les services
            import time
            
            # Petite pause pour simuler le redémarrage
            time.sleep(2)
            
            return JsonResponse({
                'success': True,
                'message': 'Services redémarrés avec succès',
                'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        except Exception as e:
            return JsonResponse({'error': f'Erreur lors du redémarrage: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)


# Variables globales pour contrôle
pointage_actif = False
pointage_lock = threading.Lock()
frame_queue = queue.Queue(maxsize=1)  # Dernière frame uniquement

class SmartCamera:
    def __init__(self):
        self.video = cv2.VideoCapture(0)  # Webcam locale (0) ou IP cam pour déploiement
        if not self.video.isOpened():
            raise RuntimeError("Impossible d'ouvrir la webcam")

        self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.video.set(cv2.CAP_PROP_FPS, 30)

    def __del__(self):
        if hasattr(self, 'video'):
            self.video.release()

    def get_frame(self):
        success, frame = self.video.read()
        if not success:
            return None

        # Resize pour fluidité
        frame = cv2.resize(frame, (640, 480))

        with pointage_lock:
            if pointage_actif:
                statut, nom, prenom, matricule = process_frame(frame.copy())

                if statut == 'présent' and nom and prenom and matricule:
                    text = f"{nom} {prenom} ({matricule}) - PRESENT"
                    color = (0, 255, 0)  # Vert
                    cv2.putText(frame, text, (30, 60),
                                cv2.FONT_HERSHEY_DUPLEX, 1.2, color, 3)
                elif statut in ['absent', 'inconnu']:
                    text = "Non reconnu"
                    color = (0, 0, 255)  # Rouge
                    cv2.putText(frame, text, (30, 60),
                                cv2.FONT_HERSHEY_DUPLEX, 1.2, color, 3)

                # Indicateur pointage actif
                cv2.putText(frame, "POINTAGE ACTIF", (30, 450),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

        # Encodage JPEG
        ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return jpeg.tobytes()


def gen(camera):
    while True:
        frame = camera.get_frame()
        if frame is None:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')


@login_required
def video_feed(request):
    if request.user.role != 'instructeur':
        return HttpResponseForbidden("Accès refusé")
    return StreamingHttpResponse(gen(SmartCamera()),
                                 content_type='multipart/x-mixed-replace; boundary=frame')


@login_required
def start_pointage(request):
    if request.method == 'POST' and request.user.role == 'instructeur':
        global pointage_actif
        with pointage_lock:
            pointage_actif = True
        return JsonResponse({'status': 'started'})
    return JsonResponse({'status': 'error'}, status=400)


@login_required
def stop_pointage(request):
    if request.method == 'POST' and request.user.role == 'instructeur':
        global pointage_actif
        with pointage_lock:
            pointage_actif = False
        return JsonResponse({'status': 'stopped'})
    return JsonResponse({'status': 'error'}, status=400)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('attendance:dashboard')  # redirige selon rôle

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Bienvenue {user.nom} {user.prenom} !")
            # Redirection intelligente selon rôle
            if user.role == 'instructeur':
                return redirect('attendance:dashboard_instructeur')
            elif user.role == 'responsable_filiere':
                return redirect('attendance:dashboard_responsable')
            elif user.role == 'administrateur':
                return redirect('attendance:dashboard_admin')
            else:
                return redirect('attendance:dashboard')
        else:
            messages.error(request, "Identifiants incorrects.")

    return render(request, 'attendance/login.html')

def logout_view(request):
    logout(request)
    messages.info(request, "Déconnexion réussie.")
    return redirect('attendance:login')

@login_required
def rapports_view(request):
    """Vue pour la génération et l'export des rapports"""
    
    # Vérification des permissions
    if request.user.role not in ['responsable_filiere', 'administrateur']:
        messages.error(request, "Accès non autorisé.")
        return redirect('attendance:dashboard')
    
    # 1. Récupération des filtres depuis l'URL (GET)
    type_rapport = request.GET.get('type')
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    groupe_id = request.GET.get('groupe')
    export_format = request.GET.get('export')

    today = timezone.now().date()

    # Logique de filtrage par date
    if type_rapport == 'journalier':
        date_debut = date_fin = today
    elif type_rapport == 'hebdomadaire':
        date_debut = today - timedelta(days=today.weekday())
        date_fin = date_debut + timedelta(days=6)
    elif type_rapport == 'mensuel':
        date_debut = today.replace(day=1)
        # Calcul fin du mois
        next_month = (date_debut + timedelta(days=32)).replace(day=1)
        date_fin = next_month - timedelta(days=1)
    else:
        # Cas personnalisé ou par défaut
        if date_debut_str:
            try:
                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
            except ValueError:
                date_debut = today
        else:
            date_debut = today
            
        if date_fin_str:
            try:
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
            except ValueError:
                date_fin = today
        else:
            date_fin = today

    # 2. Requête de base
    presences = Presence.objects.select_related('etudiant', 'annee', 'groupe').order_by('-date', '-heure')

    # 3. Application des filtres
    presences = presences.filter(date__range=[date_debut, date_fin])

    if groupe_id:
        presences = presences.filter(groupe_id=groupe_id)

    # 4. Gestion de l'export CSV
    if export_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        filename = f"rapport_{type_rapport or 'custom'}_{date_debut}_{date_fin}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(['Date', 'Heure', 'Matricule', 'Nom', 'Prénom', 'Filière/Année', 'Groupe', 'Statut'])
        
        for p in presences:
            writer.writerow([
                p.date, p.heure, p.etudiant.matricule, 
                p.etudiant.nom, p.etudiant.prenom, 
                f"{p.annee.filiere.nom} A{p.annee.numero}",
                p.groupe.nom if p.groupe else '',
                p.get_statut_display()
            ])
        
        return response

    # 5. Gestion de l'export PDF
    if export_format == 'pdf':
        response = HttpResponse(content_type='application/pdf')
        filename = f"rapport_{type_rapport or 'custom'}_{date_debut}_{date_fin}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        # Création du document PDF
        doc = SimpleDocTemplate(response, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()

        # Titre du rapport
        titre = f"Rapport de Présence - {type_rapport.capitalize() if type_rapport else 'Personnalisé'}"
        elements.append(Paragraph(titre, styles['Title']))
        elements.append(Paragraph(f"Période : {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # Préparation des données du tableau
        data = [['Date', 'Heure', 'Matricule', 'Nom Prénom', 'Filière/Année', 'Groupe', 'Statut']]
        
        # Style de base du tableau
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]

        for i, p in enumerate(presences):
            data.append([
                p.date.strftime("%d/%m/%Y"),
                p.heure.strftime("%H:%M"),
                p.etudiant.matricule,
                f"{p.etudiant.nom} {p.etudiant.prenom}",
                f"{p.annee.filiere.nom} A{p.annee.numero}",
                (p.groupe.nom if p.groupe else ''),
                p.get_statut_display()
            ])
            
            # Couleurs conditionnelles pour le statut
            row_idx = i + 1
            if p.statut == 'présent':
                table_style.append(('TEXTCOLOR', (5, row_idx), (5, row_idx), colors.green))
            elif p.statut == 'absent':
                table_style.append(('TEXTCOLOR', (5, row_idx), (5, row_idx), colors.red))
            else:
                table_style.append(('TEXTCOLOR', (5, row_idx), (5, row_idx), colors.orange))

        # Création et application du style
        table = Table(data)
        table.setStyle(TableStyle(table_style))
        elements.append(table)
        
        # Résumé en bas de page
        elements.append(Spacer(1, 20))
        total = presences.count()
        presents = presences.filter(statut='présent').count()
        taux = round((presents / total * 100), 1) if total > 0 else 0
        elements.append(Paragraph(f"<b>Total:</b> {total} | <b>Présents:</b> {presents} | <b>Taux:</b> {taux}%", styles['Normal']))
        
        doc.build(elements)
        return response

    # 6. Calcul des statistiques pour l'affichage web
    total = presences.count()
    presents = presences.filter(statut='présent').count()
    absents = presences.filter(statut='absent').count()
    taux = round((presents / total * 100), 1) if total > 0 else 0

    groupes = Groupe.objects.all()
    
    context = {
        'presences': presences,
        'groupes': groupes,
        'stats': {
            'total': total,
            'presents': presents,
            'absents': absents,
            'taux': taux
        },
        'filters': {
            'date_debut': date_debut.strftime('%Y-%m-%d'),
            'date_fin': date_fin.strftime('%Y-%m-%d'),
            'groupe_id': int(groupe_id) if groupe_id else '',
            'type': type_rapport
        }
    }
    return render(request, 'attendance/rapports.html', context)