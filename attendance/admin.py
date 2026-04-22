from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (Filiere, Annee, Groupe, Matiere, Etudiant, Presence, Rapport, 
                     Classe, Eleve)  # Garder les legacy
from core.models import Utilisateur

# ==================== NOUVEAUX MODÈLES ====================

@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'type_filiere', 'duree', 'actif']
    list_filter = ['type_filiere', 'actif']
    search_fields = ['nom', 'code']
    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'code', 'type_filiere', 'duree')
        }),
        ('Détails', {
            'fields': ('description', 'actif')
        }),
    )


@admin.register(Annee)
class AnneeAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'numero', 'annee_academique', 'responsable']
    list_filter = ['filiere', 'numero', 'annee_academique']
    search_fields = ['filiere__nom', 'annee_academique']
    fieldsets = (
        ('Hiérarchie', {
            'fields': ('filiere', 'numero')
        }),
        ('Académique', {
            'fields': ('annee_academique', 'date_debut', 'date_fin')
        }),
        ('Responsable', {
            'fields': ('responsable',)
        }),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'responsable':
            kwargs['queryset'] = Utilisateur.objects.filter(role='responsable_filiere')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Groupe)
class GroupeAdmin(admin.ModelAdmin):
    list_display = ['code', 'annee', 'type_groupe', 'capacite', 'instructeur']
    list_filter = ['annee', 'type_groupe']
    search_fields = ['code', 'nom', 'annee__filiere__nom']
    fieldsets = (
        ('Identification', {
            'fields': ('nom', 'code', 'annee')
        }),
        ('Caractéristiques', {
            'fields': ('type_groupe', 'capacite', 'salle')
        }),
        ('Personnel', {
            'fields': ('instructeur',)
        }),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'instructeur':
            kwargs['queryset'] = Utilisateur.objects.filter(role='instructeur')
        elif db_field.name == 'annee':
            # Filtrer les années par filière si une filière est sélectionnée (mais Groupe n'a pas filiere direct)
            # Pour Groupe, annee détermine filiere
            pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Matiere)
class MatiereAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'annee', 'groupe', 'instructeur', 'credits', 'actif', 'filieres_list']
    list_filter = ['annee', 'groupe', 'instructeur', 'actif', 'filieres']
    search_fields = ['code', 'nom', 'instructeur__nom']
    filter_horizontal = ('filieres',)  # Interface pour M2M
    fieldsets = (
        ('Identification', {
            'fields': ('code', 'nom')
        }),
        ('Affectation', {
            'fields': ('filieres', 'annee', 'groupe')
        }),
        ('Instructeur', {
            'fields': ('instructeur',)
        }),
        ('Détails', {
            'fields': ('credits', 'heures_total', 'date_debut', 'date_fin')
        }),
        ('Administratif', {
            'fields': ('description', 'actif')
        }),
    )

    def filieres_list(self, obj):
        return ", ".join([f.nom for f in obj.filieres.all()])
    filieres_list.short_description = 'Filières'

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'filieres':
            kwargs['queryset'] = Filiere.objects.all()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'instructeur':
            kwargs['queryset'] = Utilisateur.objects.filter(role='instructeur')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Etudiant)
class EtudiantAdmin(admin.ModelAdmin):
    list_display = ['matricule', 'nom', 'prenom', 'filiere', 'annee', 'groupe', 'actif']
    list_filter = ['filiere', 'annee', 'groupe', 'actif']
    search_fields = ['matricule', 'nom', 'prenom', 'email']
    fieldsets = (
        ('Informations personnelles', {
            'fields': ('matricule', 'nom', 'prenom', 'email', 'date_naissance')
        }),
        ('Affectation', {
            'fields': ('filiere', 'annee', 'groupe')
        }),
        ('Biométrie', {
            'fields': ('photo', 'embedding')
        }),
        ('Administratif', {
            'fields': ('actif',)
        }),
    )
    readonly_fields = ['embedding']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'annee':
            # Filtrer les années par filière si une filière est sélectionnée
            filiere_id = request.POST.get('filiere') if request.method == 'POST' else None
            if filiere_id:
                kwargs['queryset'] = Annee.objects.filter(filiere_id=filiere_id)
            else:
                kwargs['queryset'] = Annee.objects.all()
        elif db_field.name == 'groupe':
            # Filtrer les groupes par année si une année est sélectionnée
            annee_id = request.POST.get('annee') if request.method == 'POST' else None
            if annee_id:
                kwargs['queryset'] = Groupe.objects.filter(annee_id=annee_id)
            else:
                kwargs['queryset'] = Groupe.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = ['etudiant', 'date', 'heure', 'matiere', 'statut', 'reconnu_par']
    list_filter = ['statut', 'date', 'annee', 'matiere', 'groupe']
    search_fields = ['etudiant__nom', 'etudiant__matricule', 'matiere__code']
    date_hierarchy = 'date'
    fieldsets = (
        ('Étudiant', {
            'fields': ('etudiant', 'annee')
        }),
        ('Cours', {
            'fields': ('matiere', 'groupe')
        }),
        ('Enregistrement', {
            'fields': ('date', 'heure', 'statut')
        }),
        ('Suivi', {
            'fields': ('reconnu_par',)
        }),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'annee':
            etudiant_id = request.POST.get('etudiant') if request.method == 'POST' else None
            if etudiant_id:
                try:
                    etudiant = Etudiant.objects.get(id=etudiant_id)
                    kwargs['queryset'] = Annee.objects.filter(filiere=etudiant.filiere)
                except Etudiant.DoesNotExist:
                    kwargs['queryset'] = Annee.objects.all()
            else:
                kwargs['queryset'] = Annee.objects.all()
        elif db_field.name == 'groupe':
            annee_id = request.POST.get('annee') if request.method == 'POST' else None
            if annee_id:
                kwargs['queryset'] = Groupe.objects.filter(annee_id=annee_id)
            else:
                kwargs['queryset'] = Groupe.objects.all()
        elif db_field.name == 'matiere':
            annee_id = request.POST.get('annee') if request.method == 'POST' else None
            if annee_id:
                kwargs['queryset'] = Matiere.objects.filter(annee_id=annee_id)
            else:
                kwargs['queryset'] = Matiere.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'reconnu_par':
            kwargs['queryset'] = Utilisateur.objects.filter(is_staff=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Rapport)
class RapportAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'type_rapport', 'filiere', 'annee', 'date_generation']
    list_filter = ['type_rapport', 'filiere', 'annee', 'date_generation']
    search_fields = ['filiere__nom', 'annee__numero']
    date_hierarchy = 'date_generation'
    fieldsets = (
        ('Type de rapport', {
            'fields': ('type_rapport',)
        }),
        ('Scope', {
            'fields': ('filiere', 'annee', 'groupe')
        }),
        ('Période', {
            'fields': ('date_debut', 'date_fin')
        }),
        ('Génération', {
            'fields': ('genere_par', 'date_generation', 'fichier')
        }),
    )
    readonly_fields = ['date_generation']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'genere_par':
            kwargs['queryset'] = Utilisateur.objects.filter(is_staff=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ==================== MODÈLES LEGACY ====================

'''
@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ['nom', 'niveau', 'annee_scolaire']
    search_fields = ['nom', 'niveau']
    fieldsets = (
        ('Informations', {
            'fields': ('nom', 'niveau', 'annee_scolaire'),
            'description': '⚠️ Modèle legacy - utiliser Filière/Année/Groupe'
        }),
    )
    readonly_fields = ['annee_scolaire']
'''


'''
@admin.register(Eleve)
class EleveAdmin(admin.ModelAdmin):
    list_display = ['matricule', 'nom', 'prenom', 'classe', 'date_naissance']
    list_filter = ['classe__niveau', 'date_naissance']
    search_fields = ['matricule', 'nom', 'prenom']
    fieldsets = (
        ('Informations personnelles', {
            'fields': ('matricule', 'nom', 'prenom', 'date_naissance')
        }),
        ('Affectation', {
            'fields': ('classe',)
        }),
        ('Biométrie', {
            'fields': ('photo', 'embedding')
        }),
    )
    readonly_fields = ['embedding']
'''


# ==================== UTILISATEUR ====================

@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ['username', 'nom', 'prenom', 'email', 'role', 'filieres_list', 'actif']
    list_filter = ['role', 'filieres', 'actif']
    search_fields = ['username', 'nom', 'email']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Informations personnelles', {'fields': ('nom', 'prenom', 'email')}),
        ('Rôle et affectation', {'fields': ('role', 'filieres')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates importantes', {'fields': ('last_login', 'date_joined', 'date_embauche')}),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Informations supplémentaires', {'fields': ('nom', 'prenom', 'role', 'email', 'filieres', 'date_embauche')}),
    )

    def filieres_list(self, obj):
        return ", ".join([f.nom for f in obj.filieres.all()])
    filieres_list.short_description = 'Filières'

    def filieres_list(self, obj):
        return ", ".join([f.nom for f in obj.filieres.all()])
    filieres_list.short_description = 'Filières'