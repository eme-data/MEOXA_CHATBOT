# Meoxa Chatbot

Plateforme SaaS de chatbot multi-tenant, deployable en Docker, avec widget embeddable, intégration Telegram et IA optionnelle via Claude.

## Fonctionnalités

- **Multi-tenant** : chaque client dispose de sa propre configuration, base de connaissances et bot isolés
- **Widget embeddable** : une seule ligne de code pour intégrer le chatbot sur n'importe quel site
- **Réponses scriptées** : moteur de règles par patterns regex, sans IA requise
- **Base de connaissances** : contenu du site indexé et recherché par mots-clés (scoring TF-IDF)
- **IA contextuelle (optionnel)** : intégration Claude API, contrainte au contenu du site uniquement
- **Intégration Telegram** : un bot par tenant, géré automatiquement
- **Dashboard admin** : interface web complète pour la gestion multi-tenant
- **HTTPS automatique** : Let's Encrypt avec renouvellement automatique
- **Déploiement Docker** : installation en une commande sur Ubuntu

## Architecture

```
Utilisateur (Widget / Telegram)
    │
    ▼
┌─────────────────────────────────┐
│  Nginx (reverse proxy + SSL)    │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│  FastAPI (src/main.py)          │
│  ├── API Admin (auth X-API-Key) │
│  ├── Widget API (public)        │
│  └── Static (dashboard admin)   │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│  ChatEngine (par tenant)        │
│  1. Règles scriptées (regex)    │
│  2. Recherche base connaissances│
│  3. Claude API (si configuré)   │
│  4. Réponse par défaut          │
└─────────────────────────────────┘
```

## Structure du projet

```
├── src/
│   ├── main.py                  # Point d'entrée FastAPI
│   ├── api/routes.py            # Endpoints REST + widget
│   ├── core/
│   │   ├── engine.py            # Moteur de chat (pipeline)
│   │   ├── scripted.py          # Réponses par patterns regex
│   │   ├── knowledge.py         # Base de connaissances (recherche)
│   │   ├── claude_provider.py   # Intégration Claude API
│   │   └── tenant.py            # Gestion multi-tenant
│   └── adapters/
│       └── telegram.py          # Adaptateur Telegram Bot
├── static/admin.html            # Dashboard admin (SPA)
├── config/
│   ├── responses.json           # Réponses scriptées par défaut
│   └── tenants/                 # Données par tenant (gitignored)
├── nginx/
│   ├── nginx.conf               # Config HTTPS (production)
│   └── nginx-init.conf          # Config HTTP (installation)
├── docker-compose.yml
├── Dockerfile
├── install.sh                   # Script d'installation Ubuntu
├── setup-ssl.sh                 # Script de mise en place HTTPS
└── .env.example                 # Variables d'environnement
```

## Installation rapide (Ubuntu)

### Prérequis

- Serveur Ubuntu (20.04+)
- Accès root
- 1 vCPU, 1 Go RAM minimum (2 vCPU / 2 Go recommandé avec Claude API)

### 1. Installation

```bash
git clone https://github.com/eme-data/MEOXA_CHATBOT.git /opt/meoxa-chatbot
cd /opt/meoxa-chatbot
sudo bash install.sh
```

Le script installe Docker, configure le firewall, génère une clé API admin et démarre le service.

A la fin de l'installation, la **clé API admin** est affichée. Notez-la.

### 2. Activation HTTPS (optionnel)

Pointez votre domaine DNS vers l'IP du serveur, puis :

```bash
# Editez .env avec votre domaine et email
nano /opt/meoxa-chatbot/.env

# Lancez le setup SSL
sudo bash /opt/meoxa-chatbot/setup-ssl.sh
```

Le certificat Let's Encrypt est renouvelé automatiquement.

## Configuration

### Variables d'environnement (.env)

| Variable | Description | Défaut |
|---|---|---|
| `ADMIN_API_KEY` | Clé d'authentification API admin | Générée à l'installation |
| `HOST` | Adresse d'écoute | `0.0.0.0` |
| `PORT` | Port interne | `8000` |
| `LOG_LEVEL` | Niveau de log | `INFO` |
| `DOMAIN` | Nom de domaine (pour SSL) | `chatbot.example.com` |
| `CERTBOT_EMAIL` | Email Let's Encrypt | `admin@example.com` |

Les tokens Telegram et clés Claude API sont configurés **par tenant** via l'API ou le dashboard.

## Utilisation

### Dashboard admin

Accédez à `http://VOTRE_IP/admin` (ou `https://VOTRE_DOMAINE/admin`).

Entrez votre clé API admin pour vous authentifier.

Le dashboard permet de :
- Créer et gérer les tenants (clients)
- Configurer les réponses scriptées (patterns regex)
- Alimenter la base de connaissances du site
- Copier le code d'intégration du widget
- Tester le chatbot en direct

### Intégration sur un site client

Ajoutez cette ligne dans le HTML du site client :

```html
<script src="https://votre-domaine/widget/TENANT_ID/embed.js"></script>
```

Le widget s'affiche automatiquement en bas à droite de la page.

### API REST

Toutes les routes admin nécessitent le header `X-API-Key`.

#### Tenants

```bash
# Lister les tenants
curl -H "X-API-Key: VOTRE_CLE" https://votre-domaine/api/tenants

# Créer un tenant
curl -X POST -H "X-API-Key: VOTRE_CLE" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"mon-client","name":"Mon Client"}' \
  https://votre-domaine/api/tenants

# Mettre à jour (ajouter Claude API, Telegram, etc.)
curl -X PUT -H "X-API-Key: VOTRE_CLE" \
  -H "Content-Type: application/json" \
  -d '{"claude_api_key":"sk-ant-...","telegram_token":"123456:ABC..."}' \
  https://votre-domaine/api/tenants/mon-client
```

#### Règles scriptées

```bash
# Ajouter une règle
curl -X POST -H "X-API-Key: VOTRE_CLE" \
  -H "Content-Type: application/json" \
  -d '{"patterns":["bonjour","salut","hello"],"response":"Bonjour ! Comment puis-je vous aider ?"}' \
  https://votre-domaine/api/tenants/mon-client/rules
```

#### Base de connaissances

```bash
# Ajouter du contenu
curl -X POST -H "X-API-Key: VOTRE_CLE" \
  -H "Content-Type: application/json" \
  -d '{"title":"Horaires","content":"Nous sommes ouverts du lundi au vendredi de 9h à 18h.","category":"faq"}' \
  https://votre-domaine/api/tenants/mon-client/knowledge
```

#### Test

```bash
# Tester une réponse
curl -X POST -H "X-API-Key: VOTRE_CLE" \
  -H "Content-Type: application/json" \
  -d '{"message":"Quels sont vos horaires ?"}' \
  https://votre-domaine/api/tenants/mon-client/test
```

### Endpoints complets

| Méthode | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | Non | Health check |
| `GET` | `/admin` | Non | Dashboard admin |
| `GET` | `/api/tenants` | Oui | Liste des tenants |
| `POST` | `/api/tenants` | Oui | Créer un tenant |
| `GET` | `/api/tenants/{id}` | Oui | Détails d'un tenant |
| `PUT` | `/api/tenants/{id}` | Oui | Modifier un tenant |
| `DELETE` | `/api/tenants/{id}` | Oui | Supprimer un tenant |
| `GET` | `/api/tenants/{id}/rules` | Oui | Liste des règles |
| `POST` | `/api/tenants/{id}/rules` | Oui | Ajouter une règle |
| `PUT` | `/api/tenants/{id}/rules/{idx}` | Oui | Modifier une règle |
| `DELETE` | `/api/tenants/{id}/rules/{idx}` | Oui | Supprimer une règle |
| `GET` | `/api/tenants/{id}/knowledge` | Oui | Liste des connaissances |
| `POST` | `/api/tenants/{id}/knowledge` | Oui | Ajouter une entrée |
| `PUT` | `/api/tenants/{id}/knowledge/{eid}` | Oui | Modifier une entrée |
| `DELETE` | `/api/tenants/{id}/knowledge/{eid}` | Oui | Supprimer une entrée |
| `POST` | `/api/tenants/{id}/test` | Oui | Tester le chatbot |
| `GET` | `/api/bots/status` | Oui | Statut des bots Telegram |
| `POST` | `/widget/{id}/chat` | Non | Endpoint chat widget |
| `GET` | `/widget/{id}/config` | Non | Config widget |
| `GET` | `/widget/{id}/embed.js` | Non | Script widget embeddable |

## Commandes utiles

```bash
# Voir les logs
cd /opt/meoxa-chatbot && docker compose logs -f

# Redémarrer
cd /opt/meoxa-chatbot && docker compose restart

# Arrêter
cd /opt/meoxa-chatbot && docker compose down

# Mettre à jour
cd /opt/meoxa-chatbot && git pull && docker compose build && docker compose up -d
```

## Stack technique

- **Backend** : Python 3.12, FastAPI, Uvicorn
- **IA** : Anthropic Claude API (optionnel)
- **Messaging** : python-telegram-bot
- **Reverse proxy** : Nginx
- **SSL** : Let's Encrypt (Certbot)
- **Conteneurisation** : Docker, Docker Compose
- **Frontend** : HTML/JS vanilla (dashboard admin + widget)

## Licence

Propriétaire - Meoxa
