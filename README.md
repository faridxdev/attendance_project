# 🎓 Système de Gestion de Présence Étudiante par Reconnaissance Faciale

![Django](https://img.shields.io/badge/Django-5.2.9-green.svg) ![Python](https://img.shields.io/badge/Python-3.11+-blue.svg) ![DeepFace](https://img.shields.io/badge/DeepFace-0.0.93-orange.svg) ![OpenCV](https://img.shields.io/badge/OpenCV-4.10.0-red.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Présentation
Application Django pour la gestion automatisée des présences étudiantes par reconnaissance faciale : enrôlement biométrique, pointage webcam, gestion fine des filières/années/groupes/matières, rapports PDF/CSV, administration avancée.

## Fonctionnalités principales
- Authentification multi-rôles (instructeur, responsable de filière, administrateur)
- Enrôlement biométrique (photo, embedding facial chiffré)
- Pointage automatique par webcam (DeepFace, OpenCV)
- Dashboards personnalisés
- Gestion des filières, années, groupes, matières, étudiants, présences, rapports
- Génération de rapports PDF/CSV
- Outils d’administration (sauvegarde, logs, intégrité, redémarrage)
- Sécurité renforcée (embeddings chiffrés, gestion des droits)

## Modèles de données
- **Utilisateur** (hérite de AbstractUser, rôles : instructeur, responsable_filière, administrateur)
- **Filiere** (nom, code, type, durée, actif)
- **Annee** (filiere, numéro, année académique, responsable)
- **Groupe** (année, nom, code, type, instructeur)
- **Matiere** (nom, code, filières, année, instructeur)
- **Etudiant** (matricule, nom, prénom, email, date_naissance, filiere, année, groupe, photo, embedding facial chiffré)
- **Presence** (étudiant, groupe, année, matière, date, heure, statut)
- **Rapport** (type, période, généré par, fichier)

## Rôles
- **Administrateur** : gestion complète, outils avancés
- **Responsable de filière** : supervision d’une filière, rapports/statistiques
- **Instructeur** : gestion des présences, enrôlement

## Utilisation
- L’administrateur configure les filières, années, groupes, matières, utilisateurs
- Les instructeurs enrôlent les étudiants (photo, affectation, embedding facial)
- Les étudiants sont pointés automatiquement par reconnaissance faciale
- Les responsables consultent les statistiques et rapports
- Outils d’administration : sauvegarde, intégrité, logs

Lancement :
```bash
python manage.py runserver
```

Principales URLs :
- `/` : connexion
- `/enroller/` : enrôlement étudiant
- `/dashboard/` : redirection selon le rôle
- `/video_feed/` : pointage automatique
- `/rapports/` : rapports
- `/admin/` : interface Django/Jazzmin

## Sécurité
- Authentification Django personnalisée (rôles, sessions sécurisées)
- Embeddings faciaux chiffrés (Fernet, clé en variable d’environnement)
- Permissions adaptées au rôle
- Protection CSRF, logs d’audit

## Déploiement
- Compatible Linux/Windows/Mac (dev : SQLite, prod : PostgreSQL recommandé)
- Docker/docker-compose fournis
- Stack recommandée : Nginx + Gunicorn + PostgreSQL

## Contribution
- Fork, branche, PR
- Respect PEP8, black, isort, flake8
- Ajouter des tests pour toute nouvelle fonctionnalité

## Licence
Projet sous licence MIT. Voir [LICENSE](LICENSE).

## Auteurs
- Développeur principal : [Votre Nom]
- Encadrant : [Nom de l’encadrant]
- Institution : [Nom de l’établissement]