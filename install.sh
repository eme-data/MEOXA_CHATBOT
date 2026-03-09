#!/bin/bash
# =============================================================
# Meoxa Chatbot - Script d'installation complète pour Ubuntu
# =============================================================
set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[MEOXA]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# =============================================================
# 1. Vérifications système
# =============================================================
log "Vérification du système..."

if [ "$(id -u)" -ne 0 ]; then
    error "Ce script doit être exécuté en tant que root (sudo ./install.sh)"
fi

if ! grep -qi "ubuntu" /etc/os-release 2>/dev/null; then
    warn "Ce script est conçu pour Ubuntu. Continuer quand même ? (y/n)"
    read -r confirm
    [ "$confirm" != "y" ] && exit 0
fi

# =============================================================
# 2. Mise à jour système + installation des dépendances
# =============================================================
log "Mise à jour du système..."
apt-get update -y
apt-get upgrade -y

log "Installation des dépendances système..."
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    dnsutils

# =============================================================
# 3. Installation de Docker
# =============================================================
if command -v docker &> /dev/null; then
    log "Docker déjà installé : $(docker --version)"
else
    log "Installation de Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    log "Docker installé : $(docker --version)"
fi

# Docker Compose (plugin)
if docker compose version &> /dev/null; then
    log "Docker Compose déjà installé : $(docker compose version)"
else
    log "Installation de Docker Compose..."
    apt-get install -y docker-compose-plugin
    log "Docker Compose installé : $(docker compose version)"
fi

# =============================================================
# 4. Configuration du projet
# =============================================================
INSTALL_DIR="/opt/meoxa-chatbot"
log "Installation dans ${INSTALL_DIR}..."

if [ -d "$INSTALL_DIR" ]; then
    warn "Le répertoire $INSTALL_DIR existe déjà."
    warn "Mettre à jour ? (y/n)"
    read -r confirm
    if [ "$confirm" = "y" ]; then
        cd "$INSTALL_DIR"
        git pull origin main
    fi
else
    git clone https://github.com/eme-data/MEOXA_CHATBOT.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# =============================================================
# 5. Configuration de l'environnement
# =============================================================
if [ ! -f .env ]; then
    log "Configuration de l'environnement..."
    cp .env.example .env

    # Générer une clé API admin aléatoire
    ADMIN_KEY=$(openssl rand -hex 24)
    sed -i "s/your-secret-admin-key-here/$ADMIN_KEY/" .env

    log "Clé API admin générée : ${BLUE}${ADMIN_KEY}${NC}"
    log "${YELLOW}IMPORTANT : Notez cette clé, elle est nécessaire pour accéder au dashboard admin.${NC}"
else
    log "Fichier .env existant conservé."
    ADMIN_KEY=$(grep ADMIN_API_KEY .env | cut -d'=' -f2)
fi

# =============================================================
# 6. Configuration du firewall
# =============================================================
log "Configuration du firewall..."
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
log "Firewall configuré (ports 22, 80, 443, 8000 ouverts)"

# =============================================================
# 7. Build et démarrage Docker
# =============================================================
log "Build de l'image Docker..."
docker compose build

# Use HTTP-only nginx config initially (SSL certs don't exist yet)
log "Démarrage du service (HTTP)..."
mkdir -p certbot/www certbot/conf
cp nginx/nginx-init.conf nginx/active.conf

docker compose up -d

# Attendre que le service soit prêt
log "Attente du démarrage du service..."
for i in {1..30}; do
    if curl -s http://localhost/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Vérification
if curl -s http://localhost/health | grep -q "ok"; then
    log "Service démarré avec succès !"
else
    error "Le service n'a pas démarré correctement. Vérifiez les logs : docker compose logs"
fi

# =============================================================
# 8. Configuration systemd (redémarrage automatique)
# =============================================================
log "Configuration du démarrage automatique..."
cat > /etc/systemd/system/meoxa-chatbot.service << 'UNIT'
[Unit]
Description=Meoxa Chatbot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/meoxa-chatbot
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable meoxa-chatbot.service
log "Service systemd configuré (redémarrage automatique au boot)"

# =============================================================
# 9. Résumé
# =============================================================
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}=============================================================${NC}"
echo -e "${GREEN}  Meoxa Chatbot - Installation terminée !${NC}"
echo -e "${GREEN}=============================================================${NC}"
echo ""
echo -e "  ${BLUE}Dashboard admin :${NC}  http://${SERVER_IP}/admin"
echo -e "  ${BLUE}API :${NC}              http://${SERVER_IP}/docs"
echo -e "  ${BLUE}Health check :${NC}     http://${SERVER_IP}/health"
echo ""
echo -e "  ${YELLOW}Clé API admin :${NC}    ${ADMIN_KEY}"
echo ""
echo -e "  ${BLUE}Commandes utiles :${NC}"
echo -e "    Voir les logs :     cd $INSTALL_DIR && docker compose logs -f"
echo -e "    Redémarrer :        cd $INSTALL_DIR && docker compose restart"
echo -e "    Arrêter :           cd $INSTALL_DIR && docker compose down"
echo -e "    Mettre à jour :     cd $INSTALL_DIR && git pull && docker compose build && docker compose up -d"
echo ""
echo -e "  ${BLUE}Prochaines étapes :${NC}"
echo -e "    1. Allez sur http://${SERVER_IP}/admin"
echo -e "    2. Entrez la clé API admin"
echo -e "    3. Créez votre premier client"
echo -e "    4. Copiez le code d'intégration sur le site client"
echo ""
echo -e "  ${YELLOW}Pour activer HTTPS :${NC}"
echo -e "    1. Pointez votre domaine DNS vers ${SERVER_IP}"
echo -e "    2. Editez .env : DOMAIN=votre-domaine.com et CERTBOT_EMAIL=votre@email.com"
echo -e "    3. Lancez : sudo bash $INSTALL_DIR/setup-ssl.sh"
echo ""
echo -e "${GREEN}=============================================================${NC}"
