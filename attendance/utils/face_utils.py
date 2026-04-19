import cv2
import numpy as np
from deepface import DeepFace
from ..models import Etudiant, Presence, Filiere, Annee, Groupe, Matiere
from django.utils import timezone
import os

def process_frame(frame: np.ndarray, matiere_id=None) -> tuple:
    """
    Traite une frame du flux : détection + reconnaissance + marquage présence
    Retourne : (statut, nom, matricule) ou (None, None, None)
    """
    try:
        # Sauvegarde temporaire de la frame
        temp_path = "temp_frame.jpg"
        cv2.imwrite(temp_path, frame)

        # Recherche dans la base (DeepFace.find compare avec dossier connu)
        results = DeepFace.find(
            img_path=temp_path,
            db_path="media/eleves_photos/",  # dossier avec photos nommées matricule.jpg
            model_name="ArcFace",
            detector_backend="retinaface",
            distance_metric="cosine",
            enforce_detection=False,
            silent=True
        )

        os.remove(temp_path)

        if len(results) > 0 and results[0].shape[0] > 0:
            best_match = results[0].iloc[0]
            if best_match["distance"] < 0.4:  # seuil de similarité (ajuste si besoin)
                matricule = best_match["identity"].split('/')[-1].split('.')[0]
                try:
                    etudiant = Etudiant.objects.get(matricule=matricule)
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
                        filiere=etudiant.filiere,
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
                    return 'présent', etudiant.nom, etudiant.matricule
                except Etudiant.DoesNotExist:
                    return 'inconnu', None, None
        return 'absent', None, None
    except Exception as e:
        print(f"Erreur reconnaissance : {e}")
        return 'erreur', None, None
    
def generate_embedding_from_file(image_path):
    try:
        embedding = DeepFace.represent(
            img_path=image_path,
            model_name="ArcFace",
            detector_backend="retinaface",
            enforce_detection=True
        )[0]["embedding"]
        return np.array(embedding, dtype=np.float32)
    except:
        return None