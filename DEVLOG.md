# Devlog — Todo App Docker

Notes de construction du projet. Pas un tutoriel, plutôt un retour sur ce qui s'est passé vraiment — dans l'ordre, avec les erreurs.

---

## Contexte

Le but n'était pas de faire une app Flask complexe. C'est un projet d'infrastructure : montrer qu'on sait déployer quelque chose proprement, pas juste lancer `python run.py`.

Architecture visée dès le départ :

```
Navigateur
  ↓ HTTPS
Nginx          reverse proxy, gère les certs
  ↓ HTTP interne
Gunicorn/Flask
  ↓
PostgreSQL     données persistantes
```

La base Flask existait déjà (app factory, SQLAlchemy, routes CRUD). Ce qui manquait c'était tout ce qui tourne autour : Dockerfile, Compose, Nginx, certificats, variables d'environnement.

Une version de l'app était fournie par l'école — j'ai gardé la mienne, un peu plus propre (meilleure gestion d'erreurs, validation côté serveur, routes plus cohérentes).

---

## Construction — dans l'ordre

### Sécurité d'abord

Avant de créer quoi que ce soit, le `.gitignore`. Si on commit un `.env` ou une clé privée SSL par accident, c'est dans l'historique Git pour toujours même si on supprime le fichier ensuite. Donc `.gitignore` en premier, toujours.

Même logique pour `.env.example` : documenter les variables nécessaires sans mettre les vraies valeurs dedans.

### Dockerfile

Rien de compliqué. Une image `python:3.11-slim`, les dépendances système pour compiler le connecteur PostgreSQL, puis les dépendances Python, puis le code.

L'ordre COPY matters : on copie `requirements.txt` avant le code pour que Docker puisse cacher la couche des dépendances. Si on modifie uniquement le code Python, le `pip install` ne retourne pas au build suivant.

### docker-compose.yml

Trois services : `db`, `flask_app`, `nginx`. Réseau interne commun, Flask sans port exposé vers l'extérieur. Seul Nginx est visible.

Les variables sensibles viennent du `.env` via `${VAR}` — pas de mot de passe en dur dans le fichier.

### Nginx

Config en deux blocs : un serveur HTTP qui redirige tout vers HTTPS, un serveur HTTPS qui proxie vers Flask. Headers de sécurité standards (HSTS, X-Frame-Options, CSP...).

Les certificats sont auto-signés (openssl, 365 jours). Le navigateur affiche un avertissement, c'est normal en local. En prod ce serait Let's Encrypt.

### Flask — corrections

Deux petites choses ajoutées sur les routes existantes :
- validation `len(title) > 200` côté serveur (le `maxlength` HTML ne protège que le formulaire, pas une requête curl directe)
- route `/health` qui retourne `{"status": "ok"}` — standard dans tout déploiement Docker, utile pour les checks de disponibilité

`run.py` : `debug=True` → `False`, et l'hôte passe de `0.0.0.0` à `127.0.0.1` pour le lancement direct (en production c'est Gunicorn qui démarre, pas ce fichier).

---

## Erreurs rencontrées

### psycopg2 — build failure

Premier `docker compose up --build`, ça plante à `pip install` :

```
fatal error: stdlib.h: No such file or directory
compilation terminated.
```

`psycopg2` se compile depuis les sources C. L'image slim n'a pas tous les headers nécessaires même avec `gcc` et `libpq-dev` installés. Solution : `psycopg2-binary`, version pré-compilée. Standard pour les environnements Docker, aucune différence fonctionnelle pour ce projet.

### Race condition db/flask

Deuxième lancement, nouvelle erreur :

```
Connection refused — Is the server running on that host and accepting TCP/IP connections?
```

`depends_on` garantit que le conteneur `db` a démarré, pas que PostgreSQL est prêt à accepter des connexions. Flask essayait de se connecter pendant l'initialisation de la base.

Correction : `healthcheck` sur le service `db` avec `pg_isready`, et `condition: service_healthy` dans le `depends_on` de Flask. Flask attend maintenant que PostgreSQL valide lui-même qu'il est opérationnel.

### Nginx — directive coupée sur deux lignes

La valeur du header `Content-Security-Policy` s'était retrouvée sur deux lignes dans le fichier. Nginx interprète chaque ligne comme une directive séparée — ça aurait planté au démarrage avec une erreur de syntaxe cryptique.

Règle retenue : une directive Nginx = une seule ligne, peu importe la longueur.

### Token GitHub — scope manquant

Premier push refusé :

```
refusing to allow a Personal Access Token to create or update workflow
without `workflow` scope
```

Le token avait le scope `repo` mais pas `workflow`. GitHub bloque explicitement les modifications de fichiers dans `.github/workflows/` sans cette permission. Token recréé avec les deux scopes.

---

## Sécurité — tests rapides

Fait en live avec curl une fois l'app déployée.

**XSS** — `<script>alert('xss')</script>` dans le formulaire. Jinja2 échappe automatiquement tout ce qui passe dans `{{ }}`. Dans le HTML rendu : `&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;`. Le navigateur affiche la chaîne, n'exécute rien.

**SQLi** — `'; DROP TABLE todos; --`. SQLAlchemy utilise des requêtes préparées, l'input est une donnée pas une instruction. La chaîne s'est retrouvée stockée telle quelle en base.

**SSTI** — `{{7*7}}`. Affiché comme `{{7*7}}`, pas `49`. La SSTI ne fonctionne que si l'input utilisateur est passé comme template (`render_template_string`). Ici on utilise `render_template` avec un fichier fixe — les accolades n'ont aucun effet.

Les deux frameworks protègent nativement sur ces trois vecteurs sans configuration supplémentaire.

---

## Fonctionnalités ajoutées en cours de route

Pas prévu au départ, ajouté parce que ça avait du sens :

- champ `due_date` sur les tâches (date optionnelle)
- calendrier mensuel navigable, rendu côté serveur avec le module Python `calendar` — pas de dépendance JS
- filtre Tout / À faire / Terminées en JS pur sur le DOM existant
- badge rouge si une tâche a une date dépassée et n'est pas terminée
- bouton "effacer les terminées"

---

## CI/CD

Un workflow GitHub Actions dans `.github/workflows/ci.yml`. Se déclenche à chaque push sur `main`.

Trois étapes :
1. vérification syntaxe Python (`py_compile` sur chaque fichier)
2. validation du `docker-compose.yml` (`docker compose config`)
3. build de l'image Flask (`docker compose build flask_app`)

Les variables d'environnement dans le workflow sont des placeholders — le pipeline n'a pas besoin d'une vraie base de données pour valider la configuration et builder l'image.

Premier run : vert.
