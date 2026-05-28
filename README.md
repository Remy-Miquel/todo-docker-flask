# 🐳 Déploiement d'une Todo App avec Docker

Ce projet montre comment déployer une application Flask en production à l'aide de Docker.
L'objectif est de passer d'un simple `python run.py` à une vraie infrastructure sécurisée,
accessible via HTTPS, et déployable n'importe où.

---

## 🏗️ Architecture

Quand un utilisateur visite l'application, sa requête passe par trois services :

```
Navigateur
    │
    ▼  HTTPS (port 443)
 Nginx          ← Reverse proxy : reçoit les requêtes, gère le HTTPS
    │
    ▼  HTTP interne (port 8000)
 Gunicorn/Flask ← L'application Python
    │
    ▼
 PostgreSQL     ← La base de données
```

- **Nginx** : le "portier". Il reçoit les visiteurs, gère le HTTPS et redirige vers Flask.
- **Gunicorn** : le serveur WSGI. Il exécute l'application Flask en production.
- **PostgreSQL** : la base de données qui stocke les tâches.

> 💡 Flask seul ne suffit pas en production : son serveur intégré est mono-thread
> et n'est pas sécurisé. Gunicorn est conçu pour gérer de vraies requêtes en parallèle.

---

## 📁 Structure du projet

```
.
├── app/
│   ├── __init__.py          # Crée l'application Flask et connecte la BDD
│   ├── models.py            # Définit la table "todos" en base de données
│   ├── routes.py            # Les routes : afficher, créer, cocher, supprimer
│   ├── static/
│   │   ├── css/style.css    # Style de l'interface
│   │   └── js/app.js        # JavaScript minimal
│   └── templates/
│       ├── base.html        # Squelette HTML commun à toutes les pages
│       ├── index.html       # Page principale (liste des tâches)
│       └── error.html       # Page d'erreur (404, 400...)
├── nginx/
│   ├── nginx.conf           # Configuration du reverse proxy
│   └── certs/
│       ├── cert.pem         # Certificat SSL (généré)
│       ├── key.pem          # Clé privée SSL (générée)
│       └── generate-ssl.sh  # Script pour générer les certificats
├── docker-compose.yml       # Orchestre les 3 services (Flask, Nginx, PostgreSQL)
├── Dockerfile               # Recette pour construire l'image Flask
├── requirements.txt         # Dépendances Python
└── run.py                   # Point d'entrée de l'application
```

---

## ✅ Prérequis

Avant de commencer, assurez-vous d'avoir installé :

- [Docker](https://docs.docker.com/get-docker/) (version 20+)
- [Docker Compose](https://docs.docker.com/compose/install/) (inclus avec Docker Desktop)

Vérifiez vos installations :

```bash
docker --version
docker compose version
```

---

## 🚀 Déploiement étape par étape

### Étape 1 — Récupérer le projet

```bash
git clone <url-du-repo>
cd Docker
```

---

### Étape 2 — Le Dockerfile

Le `Dockerfile` est la **recette** pour construire l'image de l'application Flask.
Il indique à Docker comment préparer l'environnement Python.

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Installer les dépendances système nécessaires à psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python en premier
# (optimisation du cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY app/ ./app/
COPY run.py .

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "run:app"]
```

> 💡 On installe d'abord les dépendances (`requirements.txt`) **avant** de copier le code.
> Ainsi, si on modifie uniquement le code, Docker réutilise la couche des dépendances
> depuis son cache → build beaucoup plus rapide.

> 💡 `gcc` et `libpq-dev` sont nécessaires pour compiler `psycopg2`,
> la librairie Python qui parle à PostgreSQL.

---

### Étape 3 — Générer les certificats HTTPS

Pour activer HTTPS en local, on génère un certificat **auto-signé** avec `openssl`.
Ce type de certificat est parfait pour le développement — en production, on utiliserait
Let's Encrypt.

Créez le fichier `nginx/certs/generate-ssl.sh` :

```bash
#!/bin/bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout key.pem \
    -out cert.pem \
    -subj "/C=FR/ST=Paris/L=Paris/O=TodoApp/CN=localhost"

echo "✅ Certificats générés : cert.pem et key.pem"
```

Puis générez les certificats :

```bash
cd nginx/certs
bash generate-ssl.sh
cd ../..
```

Deux fichiers sont créés :
- `cert.pem` → le certificat (public)
- `key.pem` → la clé privée (**ne jamais partager ce fichier**)

---

### Étape 4 — Configuration Nginx

Créez le fichier `nginx/nginx.conf` :

```nginx
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # Rediriger tout le trafic HTTP vers HTTPS
    server {
        listen 80;
        server_name localhost;
        return 301 https://$host$request_uri;
    }

    # Serveur HTTPS
    server {
        listen 443 ssl;
        server_name localhost;

        # Certificats SSL
        ssl_certificate     /etc/nginx/certs/cert.pem;
        ssl_certificate_key /etc/nginx/certs/key.pem;

        # Headers de sécurité
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        # Transmettre les requêtes à Flask/Gunicorn
        location / {
            proxy_pass http://flask_app:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

**Explication des headers de sécurité :**

| Header | Rôle |
|--------|------|
| `Strict-Transport-Security` | Force le navigateur à toujours utiliser HTTPS |
| `X-Content-Type-Options` | Empêche le navigateur de deviner le type de fichier |
| `X-Frame-Options` | Bloque l'intégration du site dans un `<iframe>` (anti-clickjacking) |
| `Referrer-Policy` | Limite les infos partagées quand l'utilisateur clique un lien externe |

---

### Étape 5 — Docker Compose

Le fichier `docker-compose.yml` permet de **lancer les 3 services ensemble**
avec une seule commande.

```yaml
services:

  # Base de données PostgreSQL
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: todo_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - app_network
    restart: unless-stopped

  # Application Flask (via Gunicorn)
  flask_app:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - FLASK_APP=run.py
      - FLASK_ENV=development
      - SECRET_KEY=dev_key_todo_app_2025
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/todo_db
    depends_on:
      - db
    networks:
      - app_network
    restart: unless-stopped

  # Reverse proxy Nginx
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    depends_on:
      - flask_app
    networks:
      - app_network
    restart: unless-stopped

networks:
  app_network:
    driver: bridge

volumes:
  postgres_data:
```

> 💡 `depends_on` garantit l'ordre de démarrage :
> PostgreSQL démarre avant Flask, Flask démarre avant Nginx.

> 💡 Le volume `postgres_data` permet aux données de **persister** même si
> le conteneur est supprimé.

> 💡 `:ro` (read-only) sur les volumes Nginx empêche le conteneur de modifier
> nos fichiers de configuration — bonne pratique de sécurité.

---

### Étape 6 — Lancer l'application

```bash
docker compose up --build
```

- `--build` reconstruit l'image Flask à chaque lancement (utile lors des modifications)
- Retirez `--build` pour les lancements suivants si le code n'a pas changé

Pour lancer en arrière-plan :

```bash
docker compose up --build -d
```

---

## 🌐 Accéder à l'application

Une fois les conteneurs démarrés, ouvrez votre navigateur :

```
https://localhost
```

> ⚠️ Le navigateur affichera un avertissement "certificat non approuvé"
> car notre certificat est auto-signé. C'est **normal en développement**.
> Cliquez sur "Avancé" puis "Continuer vers localhost".

---

## 🛠️ Commandes utiles

```bash
# Voir les conteneurs qui tournent
docker compose ps

# Voir les logs en temps réel
docker compose logs -f

# Voir les logs d'un seul service
docker compose logs -f flask_app

# Entrer dans un conteneur (pour déboguer)
docker compose exec flask_app bash

# Reconstruire uniquement l'image Flask
docker compose build flask_app
```

---

## 🛑 Arrêter l'application

```bash
# Arrêter sans supprimer les données
docker compose down

# Arrêter ET supprimer les données (BDD incluse)
docker compose down -v
```

---

## 🔍 Vérification rapide

| Vérification | Commande |
|---|---|
| Les 3 services tournent | `docker compose ps` |
| L'app répond | `curl -k https://localhost` |
| La BDD est accessible | `docker compose exec db psql -U postgres -d todo_db -c "\dt"` |

---

## 📚 Ce que ce projet illustre

- **Containerisation** : packager une app Python dans une image Docker portable
- **Orchestration** : gérer plusieurs services avec Docker Compose
- **Reverse proxy** : utiliser Nginx devant Gunicorn pour la performance et la sécurité
- **HTTPS** : chiffrer les communications avec un certificat SSL
- **Sécurité** : appliquer des headers HTTP pour protéger l'application
- **Persistance** : conserver les données PostgreSQL via les volumes Docker
