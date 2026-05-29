# Devlog — Todo App Docker

Notes de construction du projet. Pas un tutoriel, plutôt un retour sur ce qui s'est passé vraiment — dans l'ordre, avec les erreurs.

L'exercice de base demandait de déployer une app avec Docker. On a fait ça, puis on a continué parce que chaque étape posait naturellement la suivante. Au final le projet couvre l'infrastructure, l'authentification, l'accès distant et la sécurité. C'est plus que demandé, mais rien n'a été ajouté pour faire du volume — chaque décision avait une raison concrète.

---

## V1 — Infrastructure de base

### Contexte

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

### Construction — dans l'ordre

**Sécurité d'abord**

Avant de créer quoi que ce soit, le `.gitignore`. Si on commit un `.env` ou une clé privée SSL par accident, c'est dans l'historique Git pour toujours même si on supprime le fichier ensuite. Donc `.gitignore` en premier, toujours.

Même logique pour `.env.example` : documenter les variables nécessaires sans mettre les vraies valeurs dedans.

**Dockerfile**

Rien de compliqué. Une image `python:3.11-slim`, les dépendances système pour compiler le connecteur PostgreSQL, puis les dépendances Python, puis le code.

L'ordre COPY matters : on copie `requirements.txt` avant le code pour que Docker puisse mettre en cache la couche des dépendances. Si on modifie uniquement le code Python, le `pip install` ne retourne pas au build suivant.

**docker-compose.yml**

Trois services : `db`, `flask_app`, `nginx`. Réseau interne commun, Flask sans port exposé vers l'extérieur. Seul Nginx est visible.

Les variables sensibles viennent du `.env` via `${VAR}` — pas de mot de passe en dur dans le fichier.

**Nginx**

Config en deux blocs : un serveur HTTP qui redirige tout vers HTTPS, un serveur HTTPS qui proxie vers Flask. Headers de sécurité standards (HSTS, X-Frame-Options, CSP...).

Les certificats sont auto-signés (openssl, 365 jours). Le navigateur affiche un avertissement, c'est normal en local. En prod ce serait Let's Encrypt.

**Flask — corrections**

Deux petites choses ajoutées sur les routes existantes :
- validation `len(title) > 200` côté serveur (le `maxlength` HTML ne protège que le formulaire, pas une requête curl directe)
- route `/health` qui retourne `{"status": "ok"}` — standard dans tout déploiement Docker, utile pour les checks de disponibilité

`run.py` : `debug=True` → `False`, et l'hôte passe de `0.0.0.0` à `127.0.0.1` pour le lancement direct (en production c'est Gunicorn qui démarre, pas ce fichier).

---

### Erreurs rencontrées en V1

**psycopg2 — build failure**

Premier `docker compose up --build`, ça plante à `pip install` :

```
fatal error: stdlib.h: No such file or directory
compilation terminated.
```

`psycopg2` se compile depuis les sources C. L'image slim n'a pas tous les headers nécessaires même avec `gcc` et `libpq-dev` installés. Solution : `psycopg2-binary`, version pré-compilée. Standard pour les environnements Docker, aucune différence fonctionnelle pour ce projet.

**Race condition db/flask**

Deuxième lancement, nouvelle erreur :

```
Connection refused — Is the server running on that host and accepting TCP/IP connections?
```

`depends_on` garantit que le conteneur `db` a démarré, pas que PostgreSQL est prêt à accepter des connexions. Flask essayait de se connecter pendant l'initialisation de la base.

Correction : `healthcheck` sur le service `db` avec `pg_isready`, et `condition: service_healthy` dans le `depends_on` de Flask. Flask attend maintenant que PostgreSQL valide lui-même qu'il est opérationnel.

**Nginx — directive coupée sur deux lignes**

La valeur du header `Content-Security-Policy` s'était retrouvée sur deux lignes dans le fichier. Nginx interprète chaque ligne comme une directive séparée — ça aurait planté au démarrage avec une erreur de syntaxe cryptique.

Règle retenue : une directive Nginx = une seule ligne, peu importe la longueur.

**Token GitHub — scope manquant**

Premier push refusé :

```
refusing to allow a Personal Access Token to create or update workflow
without `workflow` scope
```

Le token avait le scope `repo` mais pas `workflow`. GitHub bloque explicitement les modifications de fichiers dans `.github/workflows/` sans cette permission. Token recréé avec les deux scopes.

---

### Sécurité — tests rapides V1

Fait en live avec curl une fois l'app déployée.

**XSS** — `<script>alert('xss')</script>` dans le formulaire. Jinja2 échappe automatiquement tout ce qui passe dans `{{ }}`. Dans le HTML rendu : `&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;`. Le navigateur affiche la chaîne, n'exécute rien.

**SQLi** — `'; DROP TABLE todos; --`. SQLAlchemy utilise des requêtes préparées, l'input est une donnée pas une instruction. La chaîne s'est retrouvée stockée telle quelle en base.

**SSTI** — `{{7*7}}`. Affiché comme `{{7*7}}`, pas `49`. La SSTI ne fonctionne que si l'input utilisateur est passé comme template (`render_template_string`). Ici on utilise `render_template` avec un fichier fixe — les accolades n'ont aucun effet.

Les deux frameworks protègent nativement sur ces trois vecteurs sans configuration supplémentaire.

---

### Fonctionnalités ajoutées en cours de route

Pas prévu au départ, ajouté parce que ça avait du sens :

- champ `due_date` sur les tâches (date optionnelle)
- calendrier mensuel navigable, rendu côté serveur avec le module Python `calendar` — pas de dépendance JS
- filtre Tout / À faire / Terminées en JS pur sur le DOM existant
- badge rouge si une tâche a une date dépassée et n'est pas terminée
- bouton "effacer les terminées"

---

### CI/CD

Un workflow GitHub Actions dans `.github/workflows/ci.yml`. Se déclenche à chaque push sur `main`.

Trois étapes :
1. vérification syntaxe Python (`py_compile` sur chaque fichier)
2. validation du `docker-compose.yml` (`docker compose config`)
3. build de l'image Flask (`docker compose build flask_app`)

Les variables d'environnement dans le workflow sont des placeholders — le pipeline n'a pas besoin d'une vraie base de données pour valider la configuration et builder l'image.

Premier run : vert.

---

## V2 — Authentification et accès distant

### Contexte

Deux objectifs pour cette version :

1. **Ajouter un vrai système d'utilisateurs** — chaque personne a son propre compte et ne voit que ses tâches.
2. **Rendre l'app accessible à distance** — via ngrok, sans déployer sur un vrai serveur. L'objectif c'est la démo, pas la prod.

C'est aussi le moment où l'app devient "vraiment en ligne". Ça change la donne côté sécurité — les tests XSS et SQLi de la V1 c'était en local. Là, n'importe qui sur Internet peut envoyer des requêtes.

---

### Authentification — choix techniques

**Flask-Login** pour gérer les sessions. La librairie s'occupe de tout : stocker l'utilisateur en session, vérifier qu'il est connecté, rediriger vers `/login` si ce n'est pas le cas. Le décorateur `@login_required` sur chaque route todo évite de réécrire ce contrôle partout.

**Werkzeug** pour les mots de passe. Werkzeug est déjà dans les dépendances de Flask, donc pas de nouvelle dépendance. `generate_password_hash` utilise pbkdf2:sha256 avec un sel aléatoire — les mots de passe ne sont jamais stockés en clair en base.

**Deux tables** : `users` (id, username, email, password_hash) et `todos` avec une clé étrangère `user_id`. Chaque requête todo est filtrée par `current_user.id`. Un utilisateur ne peut pas lire, modifier ou supprimer les tâches d'un autre, même en forgeant un ID dans l'URL — les routes vérifient avec `filter_by(id=todo_id, user_id=current_user.id)`.

**Choix d'architecture** : les routes d'auth dans un blueprint séparé (`app/auth.py`). Ça garde `routes.py` centré sur la logique todo, et ça aurait du sens si le projet grandissait.

---

### DB reset — décision délibérée

L'ajout de `user_id NOT NULL` sur la table `todos` existante implique une migration. Pour un projet de test/démo, le choix le plus simple c'est de repartir d'une base vierge :

```bash
docker compose down -v   # supprime le volume postgres
docker compose up --build -d
```

En production on aurait utilisé Flask-Migrate (Alembic). Ici c'est inutile — l'objectif c'est de montrer l'infrastructure, pas de préserver des données de test.

---

### ngrok — pourquoi et comment

L'alternative à ngrok c'est un vrai déploiement cloud (VPS, Railway, Render...). Pour une démo rapide, ngrok est suffisant et ça évite de gérer un serveur distant, un nom de domaine, des certificats Let's Encrypt.

**Intégration dans Docker Compose** : ngrok tourne dans un 4ème conteneur, dans le même réseau Docker que nginx. Il tunnele vers `nginx:80` (HTTP interne). ngrok fournit son propre HTTPS public — il n'a pas besoin de gérer nos certificats auto-signés.

**Pourquoi le port 80 sert directement maintenant** : en V1, nginx sur le port 80 redirigait vers HTTPS (301). Si ngrok tunnelait vers ce port, il récupérait une redirection vers `https://localhost` — inaccessible depuis l'extérieur. Donc nginx sert maintenant directement sur le port 80 (HTTP, sans redirect). Le port 443 reste disponible pour l'accès local direct avec HTTPS.

Pour trouver l'URL publique après démarrage :

```bash
docker compose logs ngrok   # chercher "url=https://..."
# ou
http://localhost:4040        # dashboard ngrok
```

---

## Tests de sécurité — en ligne via ngrok

Une fois l'app accessible depuis internet, on a refait les tests. Pas juste en local cette fois.

### SQLi — toujours rien

```bash
curl -X POST https://<url-ngrok>/login \
  -d "email=' OR '1'='1&password=test"
```

Retour : page de login avec "Email ou mot de passe incorrect." SQLAlchemy transforme l'input en paramètre de requête préparée. La chaîne `' OR '1'='1` est traitée comme une valeur, pas comme du SQL. Aucune donnée n'a fuité.

### XSS — toujours rien

`<script>alert('xss')</script>` dans le titre d'une tâche. Jinja2 échappe tout ce qui passe dans `{{ }}`. Dans le HTML généré : `&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;`. Affiché comme du texte, jamais exécuté.

### CSRF — faille confirmée, puis corrigée

C'est là que ça s'est passé. On a créé un fichier HTML autonome (rien à voir avec l'app) avec un formulaire qui postait vers `/todos` :

```html
<form id="csrf" action="https://<url-ngrok>/todos" method="POST">
  <input name="title" value="Tâche injectée par CSRF">
</form>
<script>document.getElementById('csrf').submit();</script>
```

On ouvre ce fichier dans le navigateur pendant qu'on est connecté à l'app. Le formulaire s'envoie automatiquement. Résultat : la tâche "Tâche injectée par CSRF" apparaît dans la liste. Le navigateur a envoyé le cookie de session avec la requête parce que le domaine correspondait — et l'app ne vérifiait pas d'où venait la requête.

C'est une vraie vulnérabilité. Quelqu'un qui sait que tu utilises l'app pourrait t'envoyer un lien piégé, tu cliques, une action se fait à ton nom sans que tu t'en rendes compte.

**Correction — Flask-WTF**

Ajout de `Flask-WTF==1.2.1` dans les dépendances. `CSRFProtect(app)` dans `__init__.py`. Un token HMAC généré côté serveur, injecté dans chaque formulaire :

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

Flask-WTF vérifie ce token à chaque POST. S'il est absent ou invalide → 400 immédiat. Le token est signé avec la `SECRET_KEY` et expire après 1h. Un site tiers ne peut pas le connaître, donc ne peut pas forger une requête valide.

Test après correction : même fichier HTML, même tentative → **400 Bad Request**. La faille est fermée.

### Cookies — ce qu'on a vu dans DevTools

Les cookies sont visibles dans DevTools → Application → Cookies, c'est normal. Ce qui compte c'est les flags :

- `HttpOnly` : actif → JavaScript ne peut pas lire le cookie (protection XSS sur les sessions)
- `Secure` : absent → le cookie voyage en HTTP aussi (normal pour notre config, ngrok gère le HTTPS avant nginx)
- `SameSite` : Lax par défaut dans Flask — bloque les requêtes cross-site via `fetch` et XHR, mais pas les soumissions de formulaire HTML. C'est pour ça que le CSRF a fonctionné malgré Lax.

La valeur du cookie elle-même est encodée en base64 mais lisible. Ce n'est pas un problème : la payload est signée avec HMAC, elle ne peut pas être modifiée sans la `SECRET_KEY`. Même si quelqu'un lit le contenu, il ne peut pas le falsifier.

---

### Rate limiting — ajouté après les tests

Une fois la CSRF corrigée, la question suivante était évidente : rien n'empêchait un script d'essayer des milliers de mots de passe sur `/login`. Le formulaire est protégé par CSRF, mais un attaquant qui récupère d'abord le token depuis la page (ce qu'un script peut faire) peut quand même bombarder la route.

**Correction — Flask-Limiter**

Ajout de `Flask-Limiter==3.5.1`. Limite de 5 tentatives POST par minute par IP sur `/login`. Au-delà → 429 avec une page d'erreur lisible.

La clé par IP utilise le header `X-Real-IP` que nginx transmet — sinon derrière un proxy on aurait toujours l'IP interne du conteneur nginx, pas l'IP réelle du visiteur.

Stockage en mémoire : suffisant pour un seul worker Gunicorn. Si on passait à plusieurs workers ou plusieurs instances, il faudrait Redis comme backend.

Test live : 7 POST rapides avec un token CSRF valide → tentatives 1 à 5 retournent 200 (mauvais mdp), tentatives 6 et 7 retournent 429.

---

### Ce qui reste ouvert (connu, non bloquant pour la démo)

- **HTTPS non forcé sur port 80** : modifié pour ngrok, un accès HTTP direct ne redirige plus vers HTTPS. En prod ce serait à corriger.
- **Pas de validation d'email côté serveur** : on vérifie le format côté HTML (`type="email"`) mais un curl peut envoyer n'importe quoi.

---

## Conclusion — où on en est et pourquoi on s'arrête là

L'exercice demandait de déployer une app Flask avec Docker. C'est fait depuis la V1.

Ce qui a été ajouté ensuite n'était pas du remplissage. Chaque décision venait d'un besoin réel :

- **L'auth** est venue parce qu'une app sans utilisateurs c'est une app sans données. Et une app avec des données partagées entre tout le monde ça n'a pas de sens en démo.
- **ngrok** est venu parce qu'une app qu'on ne peut montrer qu'en local c'est limité. L'objectif était de montrer quelque chose qui tourne vraiment.
- **Le CSRF** est venu parce qu'une fois l'app en ligne, on a testé — et la faille était là, concrète, reproductible. On ne pouvait pas la laisser ouverte en sachant qu'elle existait.
- **Le rate limiting** est venu parce qu'après avoir corrigé le CSRF, la question suivante était évidente : est-ce qu'on peut brute-forcer le login ? On a regardé, on pouvait. Donc on a corrigé.

Ce qu'on ne fait pas : Redis pour le rate limiting en multi-workers, Flask-Migrate pour les migrations de schéma, validation d'email côté serveur, HTTPS forcé sur le port 80. Ces points existent, ils sont documentés, mais les ajouter ne changerait pas la démonstration — ce serait de l'optimisation sans objectif clair.

Le projet dans son état actuel montre quelque chose de complet : une infrastructure Docker fonctionnelle, des utilisateurs, un accès distant, et une vraie séance de tests de sécurité avec corrections à la clé. C'est suffisant, et c'est honnête.
