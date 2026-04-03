#!/usr/bin/env bash
# SwiftLot — fresh Hetzner server setup
# Run as root on a clean Ubuntu 22.04 server:
#   bash setup.sh
set -e

APP_DIR="/opt/swiftlot"
REPO="https://github.com/1anArr3d/SwiftLot.git"
PG_USER="swiftlot"
PG_PASS="swiftlot"
PG_DB="swiftlot"
SERVICE="swiftlot"

echo "==> Updating system packages"
apt-get update -y && apt-get upgrade -y

echo "==> Installing dependencies"
apt-get install -y python3 python3-pip python3-venv git postgresql postgresql-contrib xvfb

echo "==> Starting Postgres"
systemctl enable postgresql
systemctl start postgresql

echo "==> Creating Postgres user and database"
sudo -u postgres psql -c "CREATE USER $PG_USER WITH PASSWORD '$PG_PASS';" 2>/dev/null || echo "User already exists, skipping."
sudo -u postgres psql -c "CREATE DATABASE $PG_DB OWNER $PG_USER;" 2>/dev/null || echo "Database already exists, skipping."

echo "==> Cloning repo"
if [ -d "$APP_DIR" ]; then
    echo "Directory $APP_DIR already exists — pulling latest instead"
    git -C "$APP_DIR" pull
else
    git clone "$REPO" "$APP_DIR"
fi

echo "==> Setting up Python virtualenv"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

echo "==> Installing Playwright browsers"
"$APP_DIR/venv/bin/playwright" install chromium
"$APP_DIR/venv/bin/playwright" install-deps chromium

echo "==> Writing systemd service"
cat > /etc/systemd/system/$SERVICE.service <<EOF
[Unit]
Description=SwiftLot Backend
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=root
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/backend/.env
ExecStart=xvfb-run $APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE

echo ""
echo "==> Setup complete."
echo ""
echo "Next steps:"
echo "  1. Upload your .env file to $APP_DIR/backend/.env"
echo "  2. Upload swiftlot.db to $APP_DIR/backend/swiftlot.db (for migration)"
echo "  3. Run: $APP_DIR/venv/bin/python $APP_DIR/backend/migrate_sqlite_to_pg.py"
echo "  4. Run: systemctl start $SERVICE"
echo "  5. Check logs: journalctl -u $SERVICE -f"
