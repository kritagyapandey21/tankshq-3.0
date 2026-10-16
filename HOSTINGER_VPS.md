# Deploying to a fresh VPS (Hostinger or any Ubuntu server)

One server, one domain:

- Website: `https://YOUR_DOMAIN/` (static files from `frontend/`, served by Nginx with clean URLs such as `/login` and `/hub`)
- API: `https://YOUR_DOMAIN/api/...` (Nginx proxies to FastAPI on `127.0.0.1:8001`)

The pages call `/api` on the same domain, so there is nothing to configure in the frontend and no CORS to worry about.

**Use Ubuntu 24.04** (Python 3.12). Ubuntu 22.04 ships Python 3.10, which is too old for `numpy>=2.3` in `requirements.txt`.

## 0. Before you start

1. Point your domain's DNS **A record** (and `www`) at the VPS IP.
2. **Rotate the Telegram credentials** (see "Secrets" at the bottom). Do not deploy the values that are in git.
3. Have ready: Telegram API ID / hash, a fresh Telegram session string, and your Pocket Option `LO_UID` (or PO email/password).

## 1. Server packages and firewall

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nginx python3 python3-venv python3-pip ufw certbot python3-certbot-nginx
sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"
sudo ufw --force enable
```

## 2. Get the code

```bash
sudo mkdir -p /var/www
sudo git clone https://github.com/kritagyapandey21/tankshq-3.0.git /var/www/aurox
sudo chown -R $USER:$USER /var/www/aurox
```

## 3. Backend: Python environment and Chromium

```bash
cd /var/www/aurox/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Chromium for Playwright, installed system-wide so the www-data service can use it
sudo mkdir -p /opt/ms-playwright
sudo PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright ./venv/bin/playwright install --with-deps chromium
sudo chmod -R a+rX /opt/ms-playwright
```

## 4. Secrets (`.env`)

```bash
cp .env.example .env
nano .env          # fill in the real values, then:
chmod 600 .env
```

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | from https://my.telegram.org/apps |
| `TELEGRAM_SESSION_STRING` | Telethon session of the account that talks to AffiliatePocketBot |
| `REQUIRE_VERIFICATION` | keep `true` in production |
| `LO_UID` or `PO_SESSION_TOKEN` | Pocket Option session (for live pairs) |
| `ADMIN_KEY` | long random string; protects admin endpoints (`openssl rand -hex 32`) |
| `ALLOWED_ORIGINS` | `https://YOUR_DOMAIN` (only matters if you ever call the API from another origin) |
| `BYPASS_TRADER_ID` | leave unset unless you really need one bypass ID |
| `NOTIFY_TIME`, `NOTIFY_TZ` | when the daily "time to trade" notification is sent (default `10:00`, `Asia/Kolkata`) |
| `VAPID_SUBJECT` | contact for push services, e.g. `mailto:you@yourdomain.com` |

## 5. Run the backend as a service

```bash
sudo mkdir -p /var/lib/aurox
sudo chown www-data:www-data /var/lib/aurox        # SQLite database lives here
sudo chown -R root:www-data /var/www/aurox/backend/.env && sudo chmod 640 /var/www/aurox/backend/.env
sudo cp /var/www/aurox/deploy/aurox-backend.service /etc/systemd/system/aurox-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now aurox-backend
sudo systemctl status aurox-backend --no-pager
curl http://127.0.0.1:8001/health
```

Logs: `sudo journalctl -u aurox-backend -f`

## 6. Nginx

```bash
sudo sed -i 's/YOUR_DOMAIN/example.com/g' /var/www/aurox/deploy/nginx-aurox.conf   # use your real domain
sudo cp /var/www/aurox/deploy/nginx-aurox.conf /etc/nginx/sites-available/aurox
sudo ln -sf /etc/nginx/sites-available/aurox /etc/nginx/sites-enabled/aurox
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

## 7. HTTPS

```bash
sudo certbot --nginx -d example.com -d www.example.com
```

Certbot adds the HTTPS server block and the HTTP-to-HTTPS redirect, and renews automatically.

## 8. Verify

```bash
curl https://example.com/api/health
curl -I https://example.com/                       # 200
curl -s -o /dev/null -w "%{http_code}\n" https://example.com/api/trader/flags   # 401 (needs login: correct)
```

Then open the site in a browser: landing page, log in with a real Trader ID, check the hub, the terminal and the money tool.

## Daily trading notifications

Traders can tap **Enable daily reminders** on the member hub to get one motivating "time to trade" browser notification a day, even when the site is closed.

- It needs **HTTPS** (step 7). On iPhone/iPad, Apple only allows web notifications after the site is added to the Home Screen.
- A signing key pair is created automatically the first time the backend starts and saved as `vapid_keys.json` next to the database (`/var/lib/aurox/`). **Back it up and never commit it**: if it changes, every trader has to enable reminders again.
- Test the push right now (needs `ADMIN_KEY` set in `.env`):

```bash
curl -X POST https://example.com/api/push/test -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

## Admin page: updating the best performers

Open `https://example.com/admin`, enter the `ADMIN_KEY` from the server's `.env`, and edit the winners (name, ROI, photo, period label). Changes appear on the landing page and member hub immediately, with no redeploy.

- Set a **long random `ADMIN_KEY`** on the server (`openssl rand -hex 32`). Without it the admin page cannot sign in.
- Winner photos are saved in `/var/lib/aurox/uploads/` (next to the database). Include that folder in your backups.
- Until an admin saves a list, the site shows the sample winners from `frontend/config.js`.

## Updating later

```bash
cd /var/www/aurox
sudo git pull origin main
cd backend && source venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart aurox-backend
```

Static files are served straight from the repo, so a `git pull` updates the website immediately.

## Backups

Trader sessions, timezones, the "joined Telegram" flags, notification subscriptions and the best performers live in one SQLite file (plus `vapid_keys.json` and the `uploads/` folder beside it):

```bash
sudo cp /var/lib/aurox/trader_preferences.sqlite3 ~/trader_preferences.$(date +%F).sqlite3
```

To keep existing data when moving servers, copy the old `trader_preferences.sqlite3` to `/var/lib/aurox/` (owner `www-data`) before step 5.

## Secrets

`backend/.env.example` is tracked in git and currently contains what appear to be **real** Telegram credentials (API hash and a full account session string). Anyone with repo access can read them, and they remain in git history even after the file is edited.

1. Revoke the old session: in Telegram, Settings > Devices, terminate it (and regenerate the API hash at my.telegram.org if you can).
2. Create a new session string and put it only in the server's `.env`.
3. Replace the values in `.env.example` with placeholders.
4. Keep the repository private.
