# Ubuntu VPS deployment plan

This project is a private Django Admin app with background workers. Deploy it as:

- Nginx: public HTTPS entrypoint.
- Gunicorn: Django WSGI app.
- PostgreSQL: persistent app DB.
- Redis: RQ queue.
- systemd: web, worker, scheduler timer.
- No headed Pydoll on VPS: use HTTP/API parsers; use headless Pydoll only when no manual browser challenge is needed.

## Important Pydoll constraint

This VPS cannot run headed Pydoll. That means:

- Do not run `prime_pydoll_profile` on the VPS.
- Do not run `run_pydoll_monitor` on the VPS.
- Do not configure production targets with `"pydoll_headless": false`.
- Cloudflare/browser challenges that require human solving will fail on the VPS.
- Prefer `generic`, `generic_woocommerce`, `shoper_front_api`, or API replay with already captured/persisted session data.
- If a store needs manual Cloudflare solving, prime/capture on a local machine and expect the session to expire. Treat that store as fragile.

Recommended production rule: keep production checks browserless unless a target has been proven to work with headless Pydoll.

## Pre-deploy app prep

Do this in repo before first production deploy.

1. Add production WSGI server dependency:

```bash
uv add gunicorn
```

Commit `pyproject.toml` and `uv.lock`.

2. Add `STATIC_ROOT` to `config/settings.py`:

```python
STATIC_ROOT = BASE_DIR / "staticfiles"
```

3. Optional but recommended later:

- Add `CSRF_TRUSTED_ORIGINS=https://your-domain.example` env support.
- Add `SECURE_SSL_REDIRECT=true` env support.
- Add `SESSION_COOKIE_SECURE=true` and `CSRF_COOKIE_SECURE=true` for HTTPS-only cookies.

Without step 2, `collectstatic` will not have a destination for Nginx-served admin static files.

## Server assumptions

Examples use:

- Ubuntu 24.04 LTS.
- Domain: `monitor.example.com`.
- App user: `pokemony`.
- App path: `/srv/pokemony_blau`.
- systemd env file: `/etc/pokemony-blau.env`.
- Unix socket: `/run/pokemony-blau/gunicorn.sock`.

Replace names where needed.

## 1. DNS

Point DNS record to VPS IP:

```text
monitor.example.com A <VPS_IPV4>
```

Wait until:

```bash
dig +short monitor.example.com
```

returns VPS IP.

## 2. Base packages

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y nginx postgresql postgresql-contrib redis-server git curl ufw certbot python3-certbot-nginx
```

Install `uv` for the app user later, not globally.

## 3. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"
sudo ufw enable
sudo ufw status
```

## 4. App user and SSH deploy key

```bash
sudo adduser --system --group --home /srv/pokemony_blau pokemony
sudo mkdir -p /srv/pokemony_blau
sudo chown pokemony:pokemony /srv/pokemony_blau
```

Create an SSH key owned by the `pokemony` user:

```bash
sudo -u pokemony mkdir -p /srv/pokemony_blau/.ssh
sudo -u pokemony chmod 700 /srv/pokemony_blau/.ssh
sudo -u pokemony ssh-keygen -t ed25519 -C "pokemony-blau-vps" -f /srv/pokemony_blau/.ssh/id_ed25519 -N ""
```

Print the public key:

```bash
sudo -u pokemony cat /srv/pokemony_blau/.ssh/id_ed25519.pub
```

Add that public key to your repo host:

- GitHub: repo -> Settings -> Deploy keys -> Add deploy key.
- GitLab: repo -> Settings -> Repository -> Deploy keys.

Use read-only access unless the VPS must push code. For deployment, read-only is enough.

Trust the repo host key:

```bash
sudo -u pokemony sh -c 'ssh-keyscan github.com >> /srv/pokemony_blau/.ssh/known_hosts'
sudo -u pokemony chmod 600 /srv/pokemony_blau/.ssh/known_hosts
```

For GitLab, replace `github.com` with `gitlab.com` or your self-hosted GitLab domain.

Test access:

```bash
sudo -u pokemony ssh -T git@github.com
```

GitHub usually returns exit code `1`, but with a success message like:

```text
Hi <owner>/<repo>! You've successfully authenticated, but GitHub does not provide shell access.
```

Clone with the SSH URL, not HTTPS:

```bash
sudo -u pokemony git clone git@github.com:<OWNER>/<REPO>.git /srv/pokemony_blau/app
```

If your SSH key has a non-default path or your repo host needs special config, create `/srv/pokemony_blau/.ssh/config`:

```sshconfig
Host github.com
    HostName github.com
    User git
    IdentityFile /srv/pokemony_blau/.ssh/id_ed25519
    IdentitiesOnly yes
```

Then lock permissions:

```bash
sudo -u pokemony chmod 600 /srv/pokemony_blau/.ssh/config
```

## 5. App dependencies

Install `uv`:

```bash
sudo -u pokemony sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
```

Install dependencies:

```bash
cd /srv/pokemony_blau/app
sudo -u pokemony /srv/pokemony_blau/.local/bin/uv sync --frozen
```

If Python 3.14 is not already installed, `uv` should fetch the required Python from `pyproject.toml`.

## 6. PostgreSQL

Create DB and user:

```bash
sudo -u postgres psql
```

Inside `psql`:

```sql
CREATE DATABASE tcg_monitor;
CREATE USER tcg_monitor WITH PASSWORD 'replace-with-long-random-password';
ALTER ROLE tcg_monitor SET client_encoding TO 'utf8';
ALTER ROLE tcg_monitor SET default_transaction_isolation TO 'read committed';
ALTER ROLE tcg_monitor SET timezone TO 'Europe/Warsaw';
GRANT ALL PRIVILEGES ON DATABASE tcg_monitor TO tcg_monitor;
\q
```

For PostgreSQL 15+ schema permissions:

```bash
sudo -u postgres psql -d tcg_monitor -c "GRANT ALL ON SCHEMA public TO tcg_monitor;"
```

## 7. Redis

Enable Redis:

```bash
sudo systemctl enable --now redis-server
sudo systemctl status redis-server
```

Default local URL:

```text
redis://localhost:6379/0
```

## 8. Environment file

Create `/etc/pokemony-blau.env`:

```bash
sudo nano /etc/pokemony-blau.env
```

Content:

```env
DJANGO_SECRET_KEY=replace-with-long-random-secret
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=monitor.example.com,127.0.0.1,localhost

POSTGRES_DB=tcg_monitor
POSTGRES_USER=tcg_monitor
POSTGRES_PASSWORD=replace-with-long-random-password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

REDIS_URL=redis://localhost:6379/0

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_WEBHOOK_URL=
```

Lock permissions:

```bash
sudo chown root:pokemony /etc/pokemony-blau.env
sudo chmod 640 /etc/pokemony-blau.env
```

Generate secrets locally with:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(64))
PY
```

## 9. Migrate, static files, superuser

```bash
sudo systemd-run --wait --pty \
  --property=EnvironmentFile=/etc/pokemony-blau.env \
  --uid=pokemony --gid=pokemony \
  --working-directory=/srv/pokemony_blau/app \
  /srv/pokemony_blau/.local/bin/uv run python manage.py migrate
sudo systemd-run --wait --pty \
  --property=EnvironmentFile=/etc/pokemony-blau.env \
  --uid=pokemony --gid=pokemony \
  --working-directory=/srv/pokemony_blau/app \
  /srv/pokemony_blau/.local/bin/uv run python manage.py collectstatic --noinput
sudo systemd-run --wait --pty \
  --property=EnvironmentFile=/etc/pokemony-blau.env \
  --uid=pokemony --gid=pokemony \
  --working-directory=/srv/pokemony_blau/app \
  /srv/pokemony_blau/.local/bin/uv run python manage.py createsuperuser
```

## 10. Gunicorn systemd service

Create runtime dir:

```bash
sudo mkdir -p /run/pokemony-blau
sudo chown pokemony:www-data /run/pokemony-blau
```

Create `/etc/systemd/system/pokemony-blau-web.service`:

```ini
[Unit]
Description=Pokemony Blau Django web
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=pokemony
Group=www-data
WorkingDirectory=/srv/pokemony_blau/app
EnvironmentFile=/etc/pokemony-blau.env
RuntimeDirectory=pokemony-blau
RuntimeDirectoryMode=0755
ExecStart=/srv/pokemony_blau/.local/bin/uv run gunicorn config.wsgi:application \
  --bind unix:/run/pokemony-blau/gunicorn.sock \
  --workers 2 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pokemony-blau-web
sudo systemctl status pokemony-blau-web
```

Logs:

```bash
journalctl -u pokemony-blau-web -f
```

## 11. RQ worker systemd service

Create `/etc/systemd/system/pokemony-blau-worker.service`:

```ini
[Unit]
Description=Pokemony Blau RQ worker
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=pokemony
Group=pokemony
WorkingDirectory=/srv/pokemony_blau/app
EnvironmentFile=/etc/pokemony-blau.env
ExecStart=/srv/pokemony_blau/.local/bin/uv run python manage.py rqworker default
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pokemony-blau-worker
sudo systemctl status pokemony-blau-worker
```

Logs:

```bash
journalctl -u pokemony-blau-worker -f
```

## 12. Scheduler systemd timer

The scheduler command enqueues due targets once. Run it every minute with a timer.

Create `/etc/systemd/system/pokemony-blau-scheduler.service`:

```ini
[Unit]
Description=Pokemony Blau enqueue due checks
After=network.target postgresql.service redis-server.service

[Service]
Type=oneshot
User=pokemony
Group=pokemony
WorkingDirectory=/srv/pokemony_blau/app
EnvironmentFile=/etc/pokemony-blau.env
ExecStart=/srv/pokemony_blau/.local/bin/uv run python manage.py enqueue_due_checks
```

Create `/etc/systemd/system/pokemony-blau-scheduler.timer`:

```ini
[Unit]
Description=Run Pokemony Blau scheduler every minute

[Timer]
OnBootSec=30
OnUnitActiveSec=60
AccuracySec=5
Unit=pokemony-blau-scheduler.service

[Install]
WantedBy=timers.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pokemony-blau-scheduler.timer
systemctl list-timers pokemony-blau-scheduler.timer
```

Logs:

```bash
journalctl -u pokemony-blau-scheduler -f
```

## 13. Nginx

Create `/etc/nginx/sites-available/pokemony-blau`:

```nginx
server {
    listen 80;
    server_name monitor.example.com;

    client_max_body_size 10m;

    location /static/ {
        alias /srv/pokemony_blau/app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://unix:/run/pokemony-blau/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 75s;
    }
}
```

Enable:

```bash
sudo ln -s /etc/nginx/sites-available/pokemony-blau /etc/nginx/sites-enabled/pokemony-blau
sudo nginx -t
sudo systemctl reload nginx
```

## 14. HTTPS

```bash
sudo certbot --nginx -d monitor.example.com
sudo certbot renew --dry-run
```

After HTTPS works, add secure cookie/SSL settings in Django settings if not already added.

## 15. First production check

Open:

```text
https://monitor.example.com/admin/
```

Check services:

```bash
systemctl status pokemony-blau-web
systemctl status pokemony-blau-worker
systemctl status pokemony-blau-scheduler.timer
journalctl -u pokemony-blau-web -n 100 --no-pager
journalctl -u pokemony-blau-worker -n 100 --no-pager
journalctl -u pokemony-blau-scheduler -n 100 --no-pager
```

Run one target manually:

```bash
sudo systemd-run --wait --pty \
  --property=EnvironmentFile=/etc/pokemony-blau.env \
  --uid=pokemony --gid=pokemony \
  --working-directory=/srv/pokemony_blau/app \
  /srv/pokemony_blau/.local/bin/uv run python manage.py check_watch_target <watch_target_id>
```

## 16. Add production watch targets

Prefer browserless targets.

Generic WooCommerce search/category:

```bash
sudo systemd-run --wait --pty \
  --property=EnvironmentFile=/etc/pokemony-blau.env \
  --uid=pokemony --gid=pokemony \
  --working-directory=/srv/pokemony_blau/app \
  /srv/pokemony_blau/.local/bin/uv run python manage.py add_watch_target \
  "Store Name" \
  "https://store.example" \
  "https://store.example/?s=pokemon" \
  --mode search_page \
  --parser generic_woocommerce \
  --api-param "search=pokemon" \
  --api-param "per_page=100"
```

Shoper front API:

```bash
sudo systemd-run --wait --pty \
  --property=EnvironmentFile=/etc/pokemony-blau.env \
  --uid=pokemony --gid=pokemony \
  --working-directory=/srv/pokemony_blau/app \
  /srv/pokemony_blau/.local/bin/uv run python manage.py add_watch_target \
  "Strefa TCG" \
  "https://strefa-tcg.pl" \
  "https://strefa-tcg.pl/webapi/front/pl_PL/categories/177/products/PLN" \
  --mode category_page \
  --parser shoper_front_api
```

Avoid this on no-headed VPS unless proven headless-safe:

```bash
--pydoll
```

## 17. Deploy updates

```bash
cd /srv/pokemony_blau/app
sudo -u pokemony git pull
sudo -u pokemony /srv/pokemony_blau/.local/bin/uv sync --frozen
sudo systemd-run --wait --pty \
  --property=EnvironmentFile=/etc/pokemony-blau.env \
  --uid=pokemony --gid=pokemony \
  --working-directory=/srv/pokemony_blau/app \
  /srv/pokemony_blau/.local/bin/uv run python manage.py migrate
sudo systemd-run --wait --pty \
  --property=EnvironmentFile=/etc/pokemony-blau.env \
  --uid=pokemony --gid=pokemony \
  --working-directory=/srv/pokemony_blau/app \
  /srv/pokemony_blau/.local/bin/uv run python manage.py collectstatic --noinput
sudo systemctl restart pokemony-blau-web pokemony-blau-worker
sudo systemctl status pokemony-blau-web pokemony-blau-worker
```

## 18. Backups

Create backup dir:

```bash
sudo mkdir -p /var/backups/pokemony-blau
sudo chown postgres:postgres /var/backups/pokemony-blau
```

Manual backup:

```bash
sudo -u postgres pg_dump tcg_monitor | gzip > /tmp/tcg_monitor.sql.gz
sudo mv /tmp/tcg_monitor.sql.gz /var/backups/pokemony-blau/tcg_monitor-$(date +%F-%H%M).sql.gz
```

Add a daily cron/systemd timer later. Keep off-server copies.

Restore drill:

```bash
gunzip -c backup.sql.gz | sudo -u postgres psql tcg_monitor
```

## 19. Operations checklist

Daily:

- Check Django Admin `JobRun` failures.
- Check unmapped offers and confirm product mapping.
- Check notification failures.

After adding targets:

- Run manual check once.
- Confirm `Offer` row appears.
- Confirm `mapping_confirmed` only for known product matches.
- Confirm scheduler enqueues checks.

After parser failures:

- Inspect `JobRun.debug_payload`.
- Disable broken target if it starts failing repeatedly.
- Do not switch unknown parser output to `in_stock`.

## 20. Rollback

If deploy breaks:

```bash
cd /srv/pokemony_blau/app
sudo -u pokemony git log --oneline -5
sudo -u pokemony git checkout <previous_commit>
sudo -u pokemony /srv/pokemony_blau/.local/bin/uv sync --frozen
sudo systemctl restart pokemony-blau-web pokemony-blau-worker
```

If migrations already ran, inspect migration direction first. Do not blindly reverse migrations on production data.
