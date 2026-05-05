import cv2
import numpy as np
from deepface import DeepFace
from ..models import Etudiant, Presence, Filiere, Annee, Groupe, Matiere
from django.utils import timezone
import os, tempfile

def process_frame(frame: np.ndarray, matiere_id=None) -> tuple:
    """
    Traite une frame du flux : détection + reconnaissance + marquage présence
    Retourne : (statut, nom, prenom, matricule) ou (None, None, None, None)
    """
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        cv2.imwrite(temp_path, frame)

        # 1. Obtenir l'embedding du visage actuel (Pointage)
        # On utilise enforce_detection=False pour ne pas planter si le visage est mal cadré
        target_embedding = None
        try:
            results = DeepFace.represent(
                img_path=temp_path, 
                model_name="ArcFace",
                detector_backend="retinaface",
                enforce_detection=False
            )
            if results and len(results) > 0:
                target_embedding = np.array(results[0]["embedding"], dtype=np.float32)
        except Exception as e:
            print(f"Erreur DeepFace represent: {e}")

        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

        if target_embedding is None:
            return 'absent', None, None, None

        # 2. Comparaison avec les embeddings chiffrés en base de données
        etudiants = Etudiant.objects.filter(actif=True).exclude(embedding__isnull=True)
        best_match = None
        min_dist = 0.4  # Seuil de tolérance ArcFace (plus c'est bas, plus c'est strict)

        for etudiant in etudiants:
            stored_emb = etudiant.get_embedding()
            if stored_emb is None: continue
            
            # Calcul de la distance cosinus manuelle : 1 - (A.B / (|A|*|B|))
            dist = 1 - (np.dot(target_embedding, stored_emb) / (np.linalg.norm(target_embedding) * np.linalg.norm(stored_emb)))
            
            if dist < min_dist:
                min_dist = dist
                best_match = etudiant

        if best_match:
            try:
                etudiant = best_match
                # Marquer présence (1 par jour max)
                today = timezone.now().date()
                matiere = None
                if matiere_id:
                    try:
                        matiere = Matiere.objects.get(id=matiere_id)
                    except Matiere.DoesNotExist:
                        pass
                
                presence, created = Presence.objects.get_or_create(
                    etudiant=etudiant,
                    annee=etudiant.annee,
                    groupe=etudiant.groupe,
                    matiere=matiere,
                    date=today,
                    defaults={'statut': 'présent', 'heure': timezone.now().time(), 'reconnu_par': None}
                )
                if not created:
                    presence.statut = 'présent'
                    presence.heure = timezone.now().time()
                    presence.save()
                return 'présent', etudiant.nom, etudiant.prenom, etudiant.matricule
            except Exception as e:
                print(f"Erreur enregistrement presence: {e}")
        return 'absent', None, None, None
    except Exception as e:
        print(f"Erreur reconnaissance : {e}")
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        return 'erreur', None, None, None
    
def generate_embedding_from_file(image_path):
    # Essayer plusieurs détecteurs pour plus de robustesse lors de l'enrôlement
    for backend in ["retinaface", "mtcnn", "mediapipe", "opencv"]:
        try:
            results = DeepFace.represent(
                img_path=image_path,
                model_name="ArcFace",
                detector_backend=backend,
                enforce_detection=True
            )
            if results and len(results) > 0:
                return np.array(results[0]["embedding"], dtype=np.float32)
        except Exception:
            continue
    return None