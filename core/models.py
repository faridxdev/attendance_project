from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class Utilisateur(AbstractUser):
    """Utilisateur du système (Instructeur, Responsable Filière, Administrateur)"""
    ROLE_CHOICES = [
        ('instructeur', 'Instructeur'),  # Ancien: Surveillant
        ('responsable_filiere', 'Responsable de Filière'),  # Ancien: Proviseur
        ('administrateur', 'Administrateur'),
    ]
    
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='instructeur')
    
    # Optionnel: filières associées (pour instructeurs et responsables)
    filieres = models.ManyToManyField('attendance.Filiere', blank=True, related_name='utilisateurs')
    
    date_embauche = models.DateField(default=timezone.now)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f"{self.nom} {self.prenom} ({self.get_role_display()})"
    
    def get_full_name(self):
        return f"{self.nom} {self.prenom}"