# 🐳 Déploiement d'une Todo App avec Docker

![CI](https://github.com/Remy-Miquel/todo-docker-flask/actions/workflows/ci.yml/badge.svg)

Ce projet montre comment déployer une application Flask avec Docker — de zéro jusqu'à un vrai accès distant sécurisé.

L'objectif n'est pas de montrer une app sophistiquée, c'est de montrer l'infrastructure autour : Docker Compose, Nginx en reverse proxy, HTTPS, gestion d'utilisateurs, base de données, et exposition publique via ngrok.

---

## 🏗️ Architecture

```
Internet
    │
    ▼  HTTPS public (tunnel ngrok)
 ngrok           ← Expose l'app sur une URL publique sans ouvrir de port
    │
    ▼  HTTP interne (port 80)
 Nginx            ← Reverse proxy : reçoit les requêtes, gère le HTTPS local
    │
    ▼  HTTP interne (port 8000)
 Gunicorn/Flask   ← L'application Python
    │
    ▼
 PostgreSQL        ← La base de données (une table users, une table todos)
```

- **ngrok** : crée un tunnel HTTPS public vers l'app sans toucher au routeur ni aux DNS. L'URL générée est accessible depuis n'importe où.
- **Nginx** : le "portier". Gère le HTTPS local (port 443 avec cert auto-signé) et sert directement en HTTP (port 80) pour que ngrok puisse tunneler sans erreur SSL.
- **Gunicorn** : serveur WSGI, exécute Flask en production. Flask seul n'est pas fait pour ça.
- **PostgreSQL** : stocke les utilisateurs et leurs tâches. Chaque utilisateur ne voit que ses propres données.

---

## 📁 Structure du projet

```
.
├── .github/
│   └── workflows/
│       └── ci.yml              # CI — validation syntaxe, config et build à chaque push
├── app/
│   ├── __init__.py             # Crée l'app Flask, connecte SQLAlchemy et Flask-Login
│   ├── models.py               # Tables : User (avec mot de passe hashé) et Todo
│   ├── routes.py               # CRUD todo, calendrier, health check (protégés par login)
│   ├── auth.py                 # Routes d'authentification : /login /register /logout
│   ├── static/
│   │   ├── css/style.css       # Style de l'interface
│   │   └── js/app.js           # Filtre et toggle calendrier
│   └── templates/
│       ├── base.html           # Squelette HTML : header avec username et bouton logout
│       ├── index.html          # Liste, filtres, calendrier mensuel
│       ├── login.html          # Formulaire de connexion
│       ├── register.html       # Formulaire de création de compte
│       └── error.html          # Page d'erreur (404, 400...)
├── nginx/
│   ├── nginx.conf              # Port 80 : HTTP direct (pour ngrok) / Port 443 : HTTPS local
│   └── certs/
│       ├── cert.pem            # Certificat SSL auto-signé
│       ├── key.pem             # Clé privée SSL
│       └── generate-ssl.sh     # Script openssl pour générer les deux fichiers ci-dessus
├── docker-compose.yml          # Orchestre les 4 services : Flask, Nginx, PostgreSQL, ngrok
├── Dockerfile                  # Recette pour construire l'image Flask
├── .env.example                # Toutes les variables nécessaires (sans les vraies valeurs)
├── .gitignore                  # .env, clés SSL, caches Python — jamais dans Git
├── requirements.txt            # Dépendances Python
└── run.py                      # Point d'entrée de l'application
```

---

## ✅ Prérequis

- [Docker](https://docs.docker.com/get-docker/) (version 20+)
- [Docker Compose](https://docs.docker.com/compose/install/) (inclus avec Docker Desktop)
- Un compte ngrok gratuit pour l'accès distant → [ngrok.com](https://ngrok.com)

Vérifiez les installations :

```bash
docker --version
docker compose version
```

---

## 🚀 Déploiement

### Étape 1 — Récupérer le projet

```bash
git clone https://github.com/Remy-Miquel/todo-docker-flask.git
cd todo-docker-flask
```

---

### Étape 2 — Générer les certificats HTTPS

Pour le HTTPS local (port 443), on génère un certificat auto-signé. Le navigateur affiche un avertissement, c'est normal — en production on utiliserait Let's Encrypt.

```bash
cd nginx/certs
bash generate-ssl.sh
cd ../..
```

---

### Étape 3 — Configurer les variables d'environnement

```bash
cp .env.example .env
```

Modifiez `.env` avec vos propres valeurs :

```env
POSTGRES_DB=nom_de_la_base
POSTGRES_USER=nom_utilisateur
POSTGRES_PASSWORD=mot_de_passe_solide
SECRET_KEY=cle_secrete_longue_et_aleatoire
NGROK_AUTHTOKEN=votre_token_ngrok
```

> Le `NGROK_AUTHTOKEN` se récupère sur [dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken) après création d'un compte gratuit.

---

### Étape 4 — Lancer les 4 services

Si c'est la première fois (ou après un changement de schéma BDD) :

```bash
docker compose down -v           # supprime l'ancienne base si elle existe
docker compose up --build -d     # build + démarrage en arrière-plan
```

Lancements suivants (si le code n'a pas changé) :

```bash
docker compose up -d
```

---

### Étape 5 — Trouver l'URL ngrok

Au démarrage, ngrok génère une URL publique HTTPS. Deux façons de la récupérer :

```bash
# Dans les logs (chercher "url=https://...")
docker compose logs ngrok

# Ou ouvrir le dashboard ngrok dans le navigateur
http://localhost:4040
```

L'URL ressemble à `https://xxxx-xx-xx-xx.ngrok-free.app`.
Partagez-la — n'importe qui peut accéder à votre app depuis Internet.

---

## 🌐 Accès local direct

```
https://localhost        ← HTTPS avec cert auto-signé (cliquer "Avancé" si avertissement)
http://localhost         ← HTTP direct (utilisé par ngrok en interne)
```

---

## 🔒 Gestion des utilisateurs

L'app gère des comptes utilisateurs. Chaque utilisateur a son propre espace de tâches — il ne voit pas celles des autres.

- `/register` — créer un compte (username, email, mot de passe)
- `/login` — se connecter
- `/logout` — se déconnecter
- Toutes les routes todo sont protégées par `@login_required` — un utilisateur non connecté est redirigé vers `/login`

Les mots de passe sont hashés avec `werkzeug.security.generate_password_hash` (pbkdf2:sha256 + sel aléatoire). Rien n'est stocké en clair en base.

---

## 🛠️ Commandes utiles

```bash
# Voir les 4 services
docker compose ps

# Logs en temps réel
docker compose logs -f

# Logs d'un seul service
docker compose logs -f flask_app
docker compose logs ngrok

# Entrer dans un conteneur
docker compose exec flask_app bash

# Inspecter la base de données
docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB
```

---

## 🛑 Arrêter

```bash
# Arrêter sans supprimer les données
docker compose down

# Arrêter ET repartir d'une base vierge
docker compose down -v
```

---

## 🔍 Vérification rapide

| Vérification | Commande |
|---|---|
| Les 4 services tournent | `docker compose ps` |
| L'app répond en HTTP | `curl http://localhost/health` |
| L'app répond en HTTPS | `curl -k https://localhost/health` |
| L'URL ngrok est active | `docker compose logs ngrok` |
| Tables en base | `docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"` |

---

## 📚 Ce que ce projet illustre

- **Containerisation** : packager une app Python dans une image Docker portable
- **Orchestration** : gérer 4 services qui dépendent les uns des autres avec Docker Compose
- **Reverse proxy** : Nginx devant Gunicorn — séparation des responsabilités
- **HTTPS local** : certificat auto-signé pour le développement
- **Accès distant** : ngrok comme alternative simple à un déploiement cloud
- **Authentification** : sessions Flask-Login, mots de passe hashés, isolation des données par utilisateur
- **Sécurité** : headers HTTP, CSRF (Flask-WTF), rate limiting (Flask-Limiter), requêtes préparées, échappement Jinja2 — testés en conditions réelles via ngrok
