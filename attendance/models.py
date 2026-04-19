from django.db import models
from cryptography.fernet import Fernet
import os
import numpy as np

# ==================== NOUVELLES TABLES ====================

class Filiere(models.Model):
    """Filière universitaire (Licence, Master, BTS)"""
    TYPE_CHOICES = [
        ('licence', 'Licence'),
        ('master', 'Master'),
        ('bts', 'BTS'),
        ('autre', 'Autre'),
    ]
    
    nom = models.CharField(max_length=100)  # "Informatique", "Gestion"
    code = models.CharField(max_length=20, unique=True)  # "INFO", "GEST"
    type_filiere = models.CharField(max_length=20, choices=TYPE_CHOICES)
    duree = models.IntegerField()  # 2 ou 3 ans
    description = models.TextField(blank=True)
    date_creation = models.DateField(auto_now_add=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['nom']
        verbose_name = "Filière"
        verbose_name_plural = "Filières"

    def __str__(self):
        return f"{self.nom} ({self.type_filiere})"


class Annee(models.Model):
    """Année d'études dans une filière"""
    ANNEE_CHOICES = [
        (1, 'Année 1'),
        (2, 'Année 2'),
        (3, 'Année 3'),
    ]
    
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name='annees')
    numero = models.IntegerField(choices=ANNEE_CHOICES)
    annee_academique = models.CharField(max_length=20)  # "2024-2025"
    date_debut = models.DateField()
    date_fin = models.DateField()
    responsable = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, 
                                   null=True, blank=True, related_name='annees_responsables')

    class Meta:
        ordering = ['filiere', 'numero']
        unique_together = ['filiere', 'numero', 'annee_academique']
        verbose_name = "Année"
        verbose_name_plural = "Années"

    def __str__(self):
        return f"{self.filiere.nom} - Année {self.numero} ({self.annee_academique})"


class Groupe(models.Model):
    """Groupe d'étudiants (optionnel par année)"""
    TYPE_GROUPE_CHOICES = [
        ('cm', 'Cours Magistral'),
        ('td', 'Travaux Dirigés'),
        ('tp', 'Travaux Pratiques'),
        ('autre', 'Autre'),
    ]
    
    annee = models.ForeignKey(Annee, on_delete=models.CASCADE, related_name='groupes')
    nom = models.CharField(max_length=100)  # "Groupe 1", "Groupe 2"
    code = models.CharField(max_length=30)  # "G1-INFO-L1", "G2-INFO-L1"
    type_groupe = models.CharField(max_length=20, choices=TYPE_GROUPE_CHOICES, default='cm')
    capacite = models.IntegerField(default=30)
    instructeur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, 
                                   null=True, blank=True, related_name='groupes_instruire')
    salle = models.CharField(max_length=50, blank=True)
    date_creation = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['annee', 'nom']
        unique_together = ['annee', 'code']

    def __str__(self):
        return f"{self.code} - {self.nom}"


class Matiere(models.Model):
    """Matière/Cours enseignés aux étudiants"""
    nom = models.CharField(max_length=150)
    code = models.CharField(max_length=30, unique=True)  # "INFO101", "MATH201"
    description = models.TextField(blank=True)
    
    # Relations
    filieres = models.ManyToManyField(Filiere, related_name='matieres')
    annee = models.ForeignKey(Annee, on_delete=models.CASCADE, related_name='matieres')
    groupe = models.ForeignKey(Groupe, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='matieres')  # Optionnel : matière peut être commune
    instructeur = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, 
                                   null=True, blank=True, related_name='matieres_enseignees')
    
    # Métadonnées
    credits = models.IntegerField(default=3)
    heures_total = models.IntegerField(default=30)  # heures de cours prévues
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['annee', 'nom']
        verbose_name = "Matière"
        verbose_name_plural = "Matières"

    def __str__(self):
        return f"{self.code} - {self.nom} ({self.instructeur.nom if self.instructeur else 'Non assigné'})"


# ==================== TABLES RÉNOVÉES ====================

class Etudiant(models.Model):
    """Modèle pour les étudiants (ancien Eleve)"""
    matricule = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    date_naissance = models.DateField()
    
    # Relations
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name='etudiants')
    annee = models.ForeignKey(Annee, on_delete=models.CASCADE, related_name='etudiants')
    groupe = models.ForeignKey(Groupe, on_delete=models.SET_NULL, null=True, blank=True, 
                              related_name='etudiants')  # Optionnel si pas de groupe
    
    # Données biométriques
    photo = models.ImageField(upload_to='etudiants_photos/', blank=True)
    embedding = models.BinaryField(null=True, blank=True)  # Facial embedding chiffré
    
    # Métadonnées
    date_inscription = models.DateField(auto_now_add=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['nom', 'prenom']
        unique_together = ['matricule']

    def save_embedding(self, raw_embedding: np.ndarray):
        """Sauvegarde l'embedding facial chiffré"""
        key = os.getenv('ENCRYPTION_KEY').encode()
        f = Fernet(key)
        self.embedding = f.encrypt(raw_embedding.tobytes())
        self.save()

    def get_embedding(self):
        """Récupère l'embedding facial déchiffré"""
        if not self.embedding:
            return None
        key = os.getenv('ENCRYPTION_KEY').encode()
        f = Fernet(key)
        return np.frombuffer(f.decrypt(self.embedding), dtype=np.float32)

    def __str__(self):
        return f"{self.matricule} - {self.nom} {self.prenom}"


class Presence(models.Model):
    """Enregistrement de présence d'un étudiant"""
    STATUT_CHOICES = [
        ('présent', 'Présent'),
        ('absent', 'Absent'),
        ('retard', 'Retard'),
    ]
    
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='presences', null=True, blank=True)
    groupe = models.ForeignKey(Groupe, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='presences')  # Optionnel
    annee = models.ForeignKey(Annee, on_delete=models.CASCADE, related_name='presences', null=True, blank=True)
    matiere = models.ForeignKey(Matiere, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='presences')  # Nouvelle : matière du pointage
    date = models.DateField(auto_now_add=True)
    heure = models.TimeField(auto_now_add=True)
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='absent')
    reconnu_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, 
                                   null=True, blank=True)

    class Meta:
        ordering = ['-date', '-heure']
        unique_together = ['etudiant', 'date']
        verbose_name = "Présence"
        verbose_name_plural = "Présences"

    def __str__(self):
        return f"{self.etudiant} - {self.date} ({self.statut})"


class Rapport(models.Model):
    """Rapports de présence par filière/année"""
    TYPE_CHOICES = [
        ('journalier', 'Journalier'),
        ('hebdomadaire', 'Hebdomadaire'),
        ('mensuel', 'Mensuel'),
    ]
    
    type_rapport = models.CharField(max_length=20, choices=TYPE_CHOICES)
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name='rapports', null=True, blank=True)
    annee = models.ForeignKey(Annee, on_delete=models.CASCADE, related_name='rapports', null=True, blank=True)
    groupe = models.ForeignKey(Groupe, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='rapports')  # Optionnel
    
    date_debut = models.DateField()
    date_fin = models.DateField()
    genere_par = models.ForeignKey('core.Utilisateur', on_delete=models.SET_NULL, null=True)
    date_generation = models.DateTimeField(auto_now_add=True)
    fichier = models.FileField(upload_to='rapports/', blank=True, null=True)

    class Meta:
        ordering = ['-date_generation']

    def __str__(self):
        return f"{self.type_rapport} - {self.filiere.nom} - {self.date_debut} à {self.date_fin}"


# ==================== MODÈLES DE COMPATIBILITÉ (legacy) ====================

class Classe(models.Model):
    """Modèle legacy - conservé pour compatibilité"""
    nom = models.CharField(max_length=100)
    niveau = models.CharField(max_length=50)
    annee_scolaire = models.CharField(max_length=20)

    class Meta:
        verbose_name = "Classe (Legacy)"
        verbose_name_plural = "Classes (Legacy)"

    def __str__(self):
        return f"{self.nom} - {self.niveau}"


class Eleve(models.Model):
    """Modèle legacy - conservé pour compatibilité"""
    matricule = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    date_naissance = models.DateField()
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='eleves')
    photo = models.ImageField(upload_to='eleves_photos/', blank=True)
    embedding = models.BinaryField(null=True, blank=True)

    class Meta:
        verbose_name = "Élève (Legacy)"
        verbose_name_plural = "Élèves (Legacy)"

    def save_embedding(self, raw_embedding: np.ndarray):
        key = os.getenv('ENCRYPTION_KEY').encode()
        f = Fernet(key)
        self.embedding = f.encrypt(raw_embedding.tobytes())
        self.save()

    def get_embedding(self):
        if not self.embedding:
            return None
        key = os.getenv('ENCRYPTION_KEY').encode()
        f = Fernet(key)
        return np.frombuffer(f.decrypt(self.embedding), dtype=np.float32)

    def __str__(self):
        return f"{self.matricule} - {self.nom} {self.prenom}"