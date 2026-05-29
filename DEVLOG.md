# Devlog — Todo App Docker

Notes de construction du projet. Pas un tutoriel, plutôt un retour sur ce qui s'est passé vraiment — dans l'ordre, avec les erreurs.

L'exercice de base demandait de déployer une app avec Docker. On a fait ça, puis on a continué parce que chaque étape posait naturellement la suivante. Au final le projet couvre l'infrastructure, l'authentification, l'accès distant et la sécurité.

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

Une image `python:3.11-slim`, les dépendances système pour le connecteur PostgreSQL, puis les dépendances Python, puis le code.

L'ordre COPY matters : on copie `requirements.txt` avant le code pour que Docker mette en cache la couche des dépendances. Si on modifie uniquement le code Python, le `pip install` ne retourne pas au build suivant.

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

`psycopg2` se compile depuis les sources C. L'image slim n'a pas tous les headers nécessaires même avec `gcc` et `libpq-dev` installés. Solution : `psycopg2-binary`, version pré-compilée, qui embarque les bibliothèques au lieu de les compiler à l'installation. Aucune différence fonctionnelle, c'est l'usage habituel dans un conteneur.

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

**Pourquoi on s'arrête au CI et pas au CD**

Le CD c'est déployer automatiquement sur un serveur à chaque push qui passe le CI. C'est la suite logique, et dans un vrai projet c'est ce qu'on ferait.

Ici le problème c'est la cible : notre setup c'est une machine locale avec ngrok. ngrok change d'URL à chaque redémarrage, ce n'est pas un serveur. GitHub Actions ne saurait pas où envoyer le déploiement.

Ce que ça ressemblerait avec une vraie cible :

- **Docker Hub ou GHCR** : le CI build l'image et la pousse sur un registry public. L'image est versionnée, disponible, prête à être tirée par n'importe quel serveur. CD partiel — le serveur reste géré manuellement.
- **Railway ou Render** : intégration GitHub directe, chaque push sur `main` déclenche un redéploiement automatique. URL stable, HTTPS gratuit. CD complet pour un projet de cette taille.
- **VPS avec SSH** : GitHub Actions se connecte via SSH, fait un `git pull` et un `docker compose up --build`. Plus de contrôle, plus de configuration.

On s'est arrêté là. Le projet avait déjà dépassé le périmètre initial, et documenter ce que serait le CD sans l'implémenter c'est aussi une décision — pas un oubli.

---

## V2 — Authentification et accès distant

### Contexte

L'app tournait, mais tout le monde partageait les mêmes données et elle n'était visible qu'en local. Pour la démo, les deux manques évidents c'était des comptes utilisateurs et un accès depuis l'extérieur.

C'est aussi le moment où l'app devient vraiment accessible depuis internet. Ça change la donne côté sécurité — les tests XSS et SQLi de la V1 c'était en local. Là, n'importe qui peut envoyer des requêtes.

---

### Authentification — choix techniques

Pour les sessions, on a utilisé Flask-Login. Il gère tout le cycle : stocker l'utilisateur connecté, vérifier à chaque requête qu'il l'est encore, rediriger vers `/login` sinon. Le décorateur `@login_required` sur chaque route todo évite de réécrire ce contrôle partout.

Pour les mots de passe, Werkzeug était déjà dans les dépendances de Flask. `generate_password_hash` utilise pbkdf2:sha256 avec un sel aléatoire — rien n'est stocké en clair en base.

Le schéma : deux tables, `users` et `todos`, avec une clé étrangère `user_id`. Chaque requête todo est filtrée par `current_user.id`. Un utilisateur ne peut pas lire, modifier ou supprimer les tâches d'un autre, même en forgeant un ID dans l'URL — les routes vérifient avec `filter_by(id=todo_id, user_id=current_user.id)`.

Les routes d'auth sont dans un blueprint séparé (`app/auth.py`) pour garder `routes.py` centré sur la logique todo.

---

### DB reset — décision délibérée

L'ajout de `user_id NOT NULL` sur la table `todos` existante implique une migration. Pour un projet de test/démo, le plus direct c'est de repartir d'une base vierge :

```bash
docker compose down -v   # supprime le volume postgres
docker compose up --build -d
```

En production on aurait utilisé Flask-Migrate (Alembic). Ici c'est inutile — l'objectif c'est de montrer l'infrastructure, pas de préserver des données de test.

---

### ngrok — pourquoi et comment

L'alternative c'est un vrai déploiement cloud (VPS, Railway, Render...). Pour une démo, ngrok évite de gérer un serveur distant, un nom de domaine, des certificats Let's Encrypt.

ngrok tourne dans un 4ème conteneur dans le même réseau Docker que nginx. Il tunnele vers `nginx:80` et fournit son propre HTTPS public — pas besoin de nos certificats auto-signés.

En V1, nginx sur le port 80 redirigait vers HTTPS (301). Si ngrok tunnelait vers ce port, il récupérait une redirection vers `https://localhost` — inaccessible depuis l'extérieur. Nginx sert donc maintenant directement sur le port 80. Le port 443 reste disponible pour l'accès local direct.

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

On a créé un fichier HTML autonome avec un formulaire qui postait vers `/todos` :

```html
<form id="csrf" action="https://<url-ngrok>/todos" method="POST">
  <input name="title" value="Tâche injectée par CSRF">
</form>
<script>document.getElementById('csrf').submit();</script>
```

On ouvre ce fichier dans le navigateur pendant qu'on est connecté à l'app. Le formulaire s'envoie. Résultat : la tâche "Tâche injectée par CSRF" apparaît dans la liste. Le navigateur a envoyé le cookie de session parce que `SameSite=Lax` ne bloque pas les soumissions de formulaire HTML classiques — uniquement les requêtes `fetch` et XHR cross-site.

C'est une vraie vulnérabilité. Quelqu'un qui sait que tu utilises l'app pourrait t'envoyer un lien piégé, tu cliques, une action se fait à ton nom sans que tu t'en rendes compte.

**Flask-WTF** corrige ça. `CSRFProtect(app)` dans `__init__.py`, et un token HMAC dans chaque formulaire :

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

Flask-WTF vérifie ce token à chaque POST. Absent ou invalide → 400. Le token est signé avec la `SECRET_KEY` et expire après 1h. Un site tiers ne peut pas le connaître.

Test après correction : même fichier, même tentative → 400. La faille est fermée.

### Cookies — ce qu'on a vu dans DevTools

Les cookies sont visibles dans DevTools → Application → Cookies, c'est normal. Ce qui compte c'est les flags :

- `HttpOnly` : actif → JavaScript ne peut pas lire le cookie
- `Secure` : absent → le cookie voyage en HTTP aussi (normal, ngrok gère le HTTPS avant nginx)
- `SameSite` : Lax par défaut dans Flask — bloque `fetch` et XHR cross-site, pas les soumissions de formulaire

La valeur du cookie est encodée en base64 mais lisible. Ce n'est pas un problème : la payload est signée avec HMAC et ne peut pas être modifiée sans la `SECRET_KEY`.

---

### Rate limiting

Après la correction CSRF, la question suivante : rien n'empêchait un script de récupérer un token depuis la page et de tenter des milliers de mots de passe sur `/login`.

Flask-Limiter règle ça. Limite de 5 tentatives POST par minute par IP sur `/login`. Au-delà → 429.

La clé par IP utilise le header `X-Real-IP` que nginx transmet. Sans ça, toutes les requêtes arriveraient avec l'IP interne du conteneur nginx — la limite s'appliquerait globalement au lieu de s'appliquer par visiteur.

Stockage en mémoire : suffisant pour un seul worker Gunicorn. Plusieurs workers ou plusieurs instances demanderaient Redis.

Test : 7 POST rapides avec un token CSRF valide → 1 à 5 retournent 200, 6 et 7 retournent 429.

---

### Ce qui reste ouvert

- **HTTPS non forcé sur port 80** : modifié pour ngrok, un accès HTTP direct ne redirige plus vers HTTPS. En prod ce serait à corriger.
- **Validation d'email côté serveur** : le format est vérifié côté HTML (`type="email"`) mais un curl peut envoyer n'importe quoi.
- **Open redirect sur `?next=`** : corrigé. `urlparse(next_page).netloc != ''` détecte les URLs absolues vers un domaine externe et les ignore — seules les URLs relatives locales passent.

---

## V3 — Séparation des droits PostgreSQL

### Le problème

En V1 et V2, Flask se connecte à la base avec le `POSTGRES_USER` de l'image Docker officielle. Ce user est superuser — il peut créer, modifier, supprimer des tables, lire n'importe quoi. L'app n'a jamais eu besoin de ces droits, mais ils étaient là.

Le vecteur concret : une faille ORM qui laisse passer une commande DDL avec le superuser, c'est `DROP TABLE` exécuté. Avec un user limité aux lectures/écritures sur les deux tables, la même commande est refusée.

L'autre repo du portfolio documente justement ça sur PostgreSQL. Ne pas l'appliquer ici c'est un écart difficile à justifier.

---

### Ce qui change

Flask se connecte maintenant avec un `APP_DB_USER` dédié, créé au premier démarrage de la base. Droits : `SELECT`, `INSERT`, `UPDATE`, `DELETE` sur `users` et `todos`, plus `USAGE` sur les séquences. Pas de `CREATE`, `DROP`, `ALTER`.

Le superuser ne sert plus qu'à l'init du schéma — une seule fois, au premier lancement du conteneur.

---

### db.create_all()

Avant, Flask créait les tables lui-même via `db.create_all()` au démarrage. Pratique, mais ça demande les droits DDL qu'on vient d'enlever.

Le schéma est maintenant dans `db/init.sh`. L'image PostgreSQL officielle exécute automatiquement tout ce qui se trouve dans `/docker-entrypoint-initdb.d/` au premier lancement — c'est le mécanisme prévu pour ça, pas un contournement.

`db.create_all()` reste actif uniquement si l'app tourne sur SQLite (mode dev sans Docker). En production, Flask ne touche plus au DDL.

---

### Ce que ça ne règle pas

Les droits sont au niveau table, pas au niveau ligne. Un user mal filtré dans une route pourrait techniquement lire des données qui ne lui appartiennent pas. La protection reste dans le code : `filter_by(user_id=current_user.id)` sur toutes les requêtes todo.

---

## Patch — CVE-2026-42945 (Nginx)

CVE-2026-42945, alias "Nginx Rift" : heap buffer overflow dans le module `ngx_http_rewrite_module`, déclenché par les directives `rewrite`, `if` ou `set` avec des expressions non nommées (`$1`, `$2`). Score CVSS 9.2, exploitation active signalée dès le 18 mai 2026. Versions affectées : 0.6.27 à 1.30.0.

Notre config n'utilise pas ces directives — pas de `rewrite`, pas de captures non nommées. L'exploitation directe était peu probable dans ce setup. Ça ne change rien à la décision : la faille est publique, sévère et activement exploitée. Rester sur 1.25 n'aurait aucun sens.

Mise à jour `nginx:1.25-alpine` → `nginx:1.31-alpine` dans le compose. Aucun changement sur la config ni sur les autres services — le conteneur nginx est sans état, un `docker compose up -d` après `git pull` suffit à déployer le patch.

---

## Conclusion

L'exercice demandait de déployer une app Flask avec Docker. C'est fait depuis la V1.

L'auth est venue parce qu'une app sans comptes utilisateurs n'a pas grand sens en démo — tout le monde voit tout. ngrok parce qu'une app qu'on ne peut montrer qu'en local c'est limité. Le CSRF parce qu'une fois en ligne on a testé, la faille était là, reproductible, on ne pouvait pas la laisser. Le rate limiting parce qu'après le CSRF la prochaine question était évidente et la réponse prenait vingt minutes.

Ce qu'on n'a pas fait : Redis pour le rate limiting multi-workers, Flask-Migrate pour les migrations, validation email côté serveur, HTTPS forcé sur le port 80. Ces points sont documentés. Les ajouter ne changerait pas ce que le projet démontre.
