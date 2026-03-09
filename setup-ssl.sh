#!/bin/bash
# =============================================================
# Meoxa Chatbot - SSL/HTTPS Setup with Let's Encrypt
# Run this AFTER install.sh, once DNS is pointing to your server
# =============================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[MEOXA]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

INSTALL_DIR="/opt/meoxa-chatbot"
cd "$INSTALL_DIR" || error "Meoxa not installed. Run install.sh first."

# Load env
source .env 2>/dev/null || true

# =============================================================
# 1. Check domain configuration
# =============================================================
if [ -z "$DOMAIN" ] || [ "$DOMAIN" = "chatbot.example.com" ]; then
    echo -e "${YELLOW}Entrez votre nom de domaine (ex: chatbot.monsite.com):${NC}"
    read -r DOMAIN
    [ -z "$DOMAIN" ] && error "Nom de domaine requis"
    sed -i "s/DOMAIN=.*/DOMAIN=$DOMAIN/" .env
fi

if [ -z "$CERTBOT_EMAIL" ] || [ "$CERTBOT_EMAIL" = "admin@example.com" ]; then
    echo -e "${YELLOW}Entrez votre email (pour les notifications Let's Encrypt):${NC}"
    read -r CERTBOT_EMAIL
    [ -z "$CERTBOT_EMAIL" ] && error "Email requis"
    sed -i "s/CERTBOT_EMAIL=.*/CERTBOT_EMAIL=$CERTBOT_EMAIL/" .env
fi

log "Configuration SSL pour: $DOMAIN"

# =============================================================
# 2. Verify DNS
# =============================================================
log "Vérification DNS..."
SERVER_IP=$(curl -s ifconfig.me)
DNS_IP=$(dig +short "$DOMAIN" 2>/dev/null | head -1)

if [ "$SERVER_IP" != "$DNS_IP" ]; then
    warn "Le domaine $DOMAIN pointe vers $DNS_IP, mais ce serveur est $SERVER_IP"
    warn "Assurez-vous que le DNS est configuré correctement avant de continuer."
    echo -e "${YELLOW}Continuer quand même ? (y/n)${NC}"
    read -r confirm
    [ "$confirm" != "y" ] && exit 0
fi

# =============================================================
# 3. Start with HTTP-only config (for certbot challenge)
# =============================================================
log "Démarrage en mode HTTP pour le challenge Let's Encrypt..."
mkdir -p certbot/www certbot/conf

# Ensure HTTP-only config for challenge
cp nginx/nginx-init.conf nginx/active.conf
docker compose down
docker compose up -d chatbot nginx

# Wait for nginx
sleep 5

# =============================================================
# 4. Obtain SSL certificate
# =============================================================
log "Obtention du certificat SSL via Let's Encrypt..."
docker compose run --rm --profile ssl certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

if [ $? -ne 0 ]; then
    error "Échec de l'obtention du certificat. Vérifiez que le DNS pointe vers ce serveur."
fi

log "Certificat SSL obtenu !"

# =============================================================
# 5. Switch to HTTPS config
# =============================================================
log "Activation de la configuration HTTPS..."
cp nginx/nginx.conf nginx/active.conf
docker compose down
docker compose up -d

sleep 3

# Verify HTTPS
if curl -sk "https://$DOMAIN/health" | grep -q "ok"; then
    log "HTTPS actif et fonctionnel !"
else
    warn "Le service semble ne pas répondre en HTTPS. Vérifiez les logs: docker compose logs nginx"
fi

# =============================================================
# 6. Setup auto-renewal cron
# =============================================================
log "Configuration du renouvellement automatique du certificat..."
CRON_CMD="0 3 * * * cd $INSTALL_DIR && docker compose run --rm --profile ssl certbot renew --quiet && docker compose exec nginx nginx -s reload"

# Add to crontab if not already present
(crontab -l 2>/dev/null | grep -v "meoxa.*certbot"; echo "$CRON_CMD") | crontab -

log "Renouvellement automatique configuré (tous les jours à 3h)"

# =============================================================
# 7. Summary
# =============================================================
echo ""
echo -e "${GREEN}=============================================================${NC}"
echo -e "${GREEN}  SSL/HTTPS activé avec succès !${NC}"
echo -e "${GREEN}=============================================================${NC}"
echo ""
echo -e "  ${BLUE}Dashboard admin :${NC}  https://${DOMAIN}/admin"
echo -e "  ${BLUE}API docs :${NC}         https://${DOMAIN}/docs"
echo -e "  ${BLUE}Health check :${NC}     https://${DOMAIN}/health"
echo ""
echo -e "  ${BLUE}Code d'intégration widget :${NC}"
echo -e "  ${YELLOW}<script src=\"https://${DOMAIN}/widget/TENANT_ID/embed.js\"></script>${NC}"
echo ""
echo -e "  ${BLUE}Certificat SSL :${NC}   Let's Encrypt (renouvellement auto)"
echo -e "  ${BLUE}Expiration :${NC}       ~90 jours (renouvelé automatiquement)"
echo ""
echo -e "${GREEN}=============================================================${NC}"
