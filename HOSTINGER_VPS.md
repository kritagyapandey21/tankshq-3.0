# Hostinger VPS Deployment

This deployment serves the frontend and FastAPI backend from one domain:

- Website: `https://YOUR_DOMAIN/pocketoption/`
- API: `https://YOUR_DOMAIN/api`
- Internal backend port: `127.0.0.1:8001` (dedicated to AUROX)

## 1. Install server packages

```bash
sudo apt update
sudo apt install -y git nginx python3 python3-venv python3-pip
```

## 2. Clone the repository

```bash
sudo mkdir -p /var/www
sudo git clone https://github.com/kritagyapandey21/AUROX.git /var/www/aurox
sudo chown -R $USER:$USER /var/www/aurox
cd /var/www/aurox/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium
```

## 3. Add production secrets

```bash
cp /var/www/aurox/backend/.env.example /var/www/aurox/backend/.env
nano /var/www/aurox/backend/.env
```

Add the real `LO_UID` or PO credentials, Telegram values, and production settings. Never commit this file.

```dotenv
LO_UID=your_pocket_option_session
REQUIRE_VERIFICATION=true
ALLOWED_ORIGINS=https://YOUR_DOMAIN
```

## 4. Start the backend service

```bash
sudo mkdir -p /var/lib/aurox
sudo chown www-data:www-data /var/lib/aurox
sudo cp /var/www/aurox/deploy/aurox-backend.service /etc/systemd/system/aurox-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now aurox-backend
sudo systemctl status aurox-backend
curl http://127.0.0.1:8001/health
```

## 5. Configure Nginx

Replace `YOUR_DOMAIN` in the config with the real domain, then run:

```bash
sudo sed -i 's/YOUR_DOMAIN/example.com/g' /var/www/aurox/deploy/nginx-aurox.conf
sudo cp /var/www/aurox/deploy/nginx-aurox.conf /etc/nginx/sites-available/aurox
sudo ln -s /etc/nginx/sites-available/aurox /etc/nginx/sites-enabled/aurox
sudo nginx -t
sudo systemctl reload nginx
```

## 6. Enable HTTPS

Point the domain DNS A record to the VPS IP, then run:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d example.com -d www.example.com
```

## 7. Verify

```bash
curl https://example.com/api/health
curl https://example.com/api/server-time
```

Open `https://example.com/pocketoption/`. The domain root redirects there, and the frontend uses `/api`, so the browser never calls `localhost` or the old hosting API.

## Updating later

```bash
cd /var/www/aurox
sudo git pull origin main
cd backend
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart aurox-backend
```