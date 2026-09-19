import numpy as np
import cv2
from deepface import DeepFace
from ..models import Etudiant, Presence, Filiere, Annee, Groupe, Matiere
from django.utils import timezone

# Modèle et métrique utilisés partout (enrôlement + pointage) : ils doivent
# rester cohérents, sinon les distances calculées ne veulent plus rien dire.
MODEL_NAME = "ArcFace"

# Seuil officiel calibré par DeepFace pour ArcFace + distance cosinus.
# (deepface/config/threshold.py : thresholds["ArcFace"]["cosine"] = 0.68)
# L'ancienne valeur (0.4) était bien plus stricte que ce pour quoi le modèle
# a été calibré : elle rejetait comme "non reconnu" une bonne partie des
# vrais visages dès que l'angle/l'éclairage différait un peu de la photo
# d'enrôlement. C'est la cause principale du "ça ne reconnaît jamais".
COSINE_THRESHOLD = 0.68

# Cascade de backends de détection, du plus précis/robuste au plus basique.
# Utilisée à la fois pour l'enrôlement et pour le pointage, pour que les deux
# passent par le même chemin de code (avant : le pointage était câblé en dur
# sur "retinaface" seul, sans repli si ce backend échouait sur une frame).
DETECTOR_BACKENDS = ["retinaface", "mtcnn", "mediapipe", "opencv"]


class SpoofError(Exception):
    """Levée quand l'anti-spoofing détecte un visage factice (photo/écran)."""
    pass


class ImageQualityError(Exception):
    """Levée lorsqu'une image est trop mauvaise pour un enrôlement fiable."""
    pass


def validate_enrollment_image(image_path):
    """Refuse les images qui rendent l'empreinte faciale peu fiable."""
    image = cv2.imread(image_path)
    if image is None:
        raise ImageQualityError("Image illisible.")

    height, width = image.shape[:2]
    if width < 640 or height < 480:
        raise ImageQualityError("Résolution insuffisante: utilisez au moins 640x480 pixels.")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    if brightness < 35:
        raise ImageQualityError("Image trop sombre: éclairez davantage le visage.")
    if brightness > 235:
        raise ImageQualityError("Image surexposée: évitez une lumière dirigée vers la caméra.")

    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    if sharpness < 45:
        raise ImageQualityError("Image trop floue: restez immobile pendant la capture.")


def _extract_embedding(img, enforce_detection, anti_spoofing=False):
    """
    Essaie plusieurs backends de détection dans l'ordre jusqu'à ce que l'un
    d'eux trouve un visage. Retourne (embedding, face_confidence, spoof_detected).
    `img` peut être un chemin de fichier ou un tableau numpy (frame BGR).

    Si anti_spoofing=True et qu'un visage est détecté mais jugé factice
    (photo/écran présenté à la caméra), on arrête immédiatement et on
    remonte spoof_detected=True — inutile d'essayer les autres backends,
    la fraude a été détectée sur un visage bien réellement localisé.
    """
    for backend in DETECTOR_BACKENDS:
        try:
            results = DeepFace.represent(
                img_path=img,
                model_name=MODEL_NAME,
                detector_backend=backend,
                enforce_detection=enforce_detection,
                anti_spoofing=anti_spoofing,
            )
            if results and len(results) > 0:
                confidence = results[0].get("face_confidence", 1.0)
                # Avec enforce_detection=False, certains backends renvoient un
                # "faux" visage (toute l'image) avec une confiance à 0 : on
                # l'ignore pour éviter de comparer du bruit aux embeddings.
                if not enforce_detection and confidence == 0:
                    continue
                embedding = np.array(results[0]["embedding"], dtype=np.float32)
                return embedding, confidence, False
        except Exception as e:
            if "spoof" in str(e).lower() or type(e).__name__ == "SpoofDetected":
                print(f"Anti-spoofing : visage factice détecté (backend {backend})")
                return None, 0.0, True
            print(f"Backend {backend} a échoué : {e}")
            continue
    return None, 0.0, False


def process_frame(frame: np.ndarray, matiere_id=None) -> tuple:
    """
    Traite une frame du flux : détection anti-spoofing + reconnaissance + marquage présence
    Retourne : (statut, nom, prenom, matricule)
    statut ∈ {'présent', 'inconnu', 'aucun_visage', 'spoof', 'erreur'}
    """
    try:
        target_embedding, _confidence, spoof_detected = _extract_embedding(
            frame, enforce_detection=False, anti_spoofing=True
        )

        if spoof_detected:
            return 'spoof', None, None, None

        if target_embedding is None:
            return 'aucun_visage', None, None, None

        # 2. Comparaison avec les embeddings chiffrés en base de données
        etudiants = Etudiant.objects.filter(actif=True).exclude(embedding__isnull=True)
        best_match = None
        min_dist = COSINE_THRESHOLD  # Seuil de tolérance ArcFace calibré

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
        # Visage détecté mais aucun étudiant enrôlé ne correspond en dessous du seuil
        return 'inconnu', None, None, None
    except Exception as e:
        print(f"Erreur reconnaissance : {e}")
        return 'erreur', None, None, None


def generate_embedding_from_file(image_path):
    """Utilisée pour une capture unique : exige un visage net et réel."""
    embedding, _confidence, spoof_detected = _extract_embedding(
        image_path, enforce_detection=True, anti_spoofing=True
    )
    if spoof_detected:
        raise SpoofError("Visage factice détecté (photo/écran) lors de la capture.")
    return embedding


def generate_embedding_from_files(image_paths):
    """
    Enrôlement multi-angles façon Face ID : on capture plusieurs photos
    (face, gauche, droite...) et on moyenne leurs embeddings pour obtenir
    une signature plus robuste aux variations d'angle/lumière qu'une
    signature basée sur une seule photo.

    Retourne (embedding_moyen, nb_reussies, nb_total). embedding_moyen est
    None si aucune capture n'a donné de visage valide.
    Lève SpoofError si une des captures est jugée factice (photo/écran) :
    dans ce cas on rejette tout le lot plutôt que d'enrôler une signature
    partiellement frauduleuse.
    """
    embeddings = []
    for path in image_paths:
        validate_enrollment_image(path)
        embedding, _confidence, spoof_detected = _extract_embedding(
            path, enforce_detection=True, anti_spoofing=True
        )
        if spoof_detected:
            raise SpoofError("Une des captures ressemble à une photo/écran plutôt qu'à un visage réel.")
        if embedding is not None:
            # Normalisation L2 avant la moyenne : chaque capture compte pour
            # sa direction, pas pour l'intensité lumineuse de la prise de vue.
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embeddings.append(embedding / norm)

    if not embeddings:
        return None, 0, len(image_paths)

    mean_embedding = np.mean(embeddings, axis=0).astype(np.float32)
    return mean_embedding, len(embeddings), len(image_paths)