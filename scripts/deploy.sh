#!/usr/bin/env bash
# Put nutrai on a host that stays awake, and prove it is running there.
#
#     scripts/deploy.sh root@89.167.61.41          # full deploy
#     scripts/deploy.sh root@89.167.61.41 --check  # preflight only, changes nothing
#
# Why not `make deploy`: that target begins `git pull --ff-only`, which assumes
# a remote. This repo has none — every commit lives on this laptop — so the
# code is rsynced. That also means the deployed tree is whatever is checked out
# here, which the digest check at the end verifies rather than trusts.
#
# The bot polls Telegram (`start_polling`), so it makes outbound connections
# only: no public port, no reverse proxy, no Tailscale Funnel. The single
# requirement is a machine that is powered on.
set -euo pipefail

HOST="${1:?usage: scripts/deploy.sh user@host [--check]}"
CHECK="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR="/opt/nutrai"
SSH="ssh -o ConnectTimeout=8 -o BatchMode=yes"

say() { printf "\n\033[1m▸ %s\033[0m\n" "$*"; }
die() { printf "\n\033[31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
say "preflight"
[ -f "$ROOT/.env" ] || die ".env is missing; the bot has no tokens without it"
$SSH "$HOST" true 2>/dev/null || die "cannot ssh to $HOST — is the VPS powered on?"
echo "  ssh            ok"

$SSH "$HOST" 'command -v docker >/dev/null' \
  || die "docker is not installed on $HOST. Install it first:
     curl -fsSL https://get.docker.com | sh"
echo "  docker         $($SSH "$HOST" 'docker --version')"

FREE=$($SSH "$HOST" "df -Pm / | awk 'NR==2{print \$4}'")
[ "$FREE" -gt 4000 ] || die "only ${FREE} MB free on $HOST; USDA needs ~3 GB"
echo "  disk           ${FREE} MB free"

DUMP=$(ls -1t "${NUTRAI_BACKUP_DIR:-$HOME/nutrai-backups}"/nutrai-*.sql.gz | head -1)
[ -f "$DUMP" ] || die "no backup to migrate; run 'make backup' first"
echo "  dump           $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"

if [ "$CHECK" = "--check" ]; then say "preflight only — nothing changed"; exit 0; fi

# ------------------------------------------------- one poller, and one only
# Telegram allows a single getUpdates consumer per token. Two bots polling the
# same token do not share the work — they take turns losing, with 409s and
# meals landing on whichever happened to win. So the laptop's bot stops before
# the server's starts, and that is the whole migration cutover.
say "stopping the local bot (Telegram allows one poller per token)"
(cd "$ROOT" && docker compose stop bot >/dev/null 2>&1) || true
echo "  local bot      stopped"

# ------------------------------------------------------------------ code
say "copying the tree to $HOST:$REMOTE_DIR"
$SSH "$HOST" "mkdir -p $REMOTE_DIR"
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.claude/worktrees' --exclude 'nutrai-backups' \
  --exclude '*.pyc' --exclude '.pytest_cache' \
  "$ROOT/" "$HOST:$REMOTE_DIR/"
scp -q "$ROOT/.env" "$HOST:$REMOTE_DIR/.env"
$SSH "$HOST" "chmod 600 $REMOTE_DIR/.env"
echo "  code + .env    copied (.env chmod 600)"

# ------------------------------------------------------------------ data
say "database"
$SSH "$HOST" "cd $REMOTE_DIR && docker compose up -d db" >/dev/null
$SSH "$HOST" "cd $REMOTE_DIR && for i in \$(seq 1 60); do
    docker compose exec -T db pg_isready -U nutrai -d nutrai >/dev/null 2>&1 && exit 0
    sleep 2; done; exit 1" || die "postgres did not come up on $HOST"
echo "  postgres       healthy"

REMOTE_ENTRIES=$($SSH "$HOST" "cd $REMOTE_DIR && docker compose exec -T db psql -U nutrai -d nutrai -t -A -c \
  \"SELECT count(*) FROM log_entry\" 2>/dev/null" || echo 0)
if [ "${REMOTE_ENTRIES:-0}" -gt 0 ]; then
  # Restoring over a live diary would replace entries confirmed on the server
  # with an older laptop copy. Refuse: this script migrates *to* an empty
  # database, and anything else is a merge, which is a different job.
  die "$HOST already holds $REMOTE_ENTRIES log entries.
     Refusing to restore over them — that would overwrite server-side history
     with this laptop's copy. Restore by hand if that is really what you want."
fi

gzip -dc "$DUMP" | $SSH "$HOST" "cd $REMOTE_DIR && docker compose exec -T db psql -q -U nutrai -d nutrai" >/dev/null
echo "  restored       $(basename "$DUMP")"

# ------------------------------------------------------------------ run
say "starting the bot"
$SSH "$HOST" "cd $REMOTE_DIR && docker compose up -d --build bot" >/dev/null
sleep 8

# -------------------------------------------------------------- verify
say "verifying"
LOCAL_DIGEST=$(python3 "$ROOT/scripts/pkgdigest.py" "$ROOT/nutrai")
REMOTE_DIGEST=$($SSH "$HOST" "cd $REMOTE_DIR && docker compose exec -T bot python3 /app/scripts/pkgdigest.py /app/nutrai" | tr -d '\r')
[ "$LOCAL_DIGEST" = "$REMOTE_DIGEST" ] \
  || die "the container is running different code: local $LOCAL_DIGEST, remote $REMOTE_DIGEST"
echo "  code           $REMOTE_DIGEST (matches this laptop)"

$SSH "$HOST" "cd $REMOTE_DIR && docker compose logs --tail=200 bot" | grep -q "Run polling" \
  || die "the bot did not start polling; check: ssh $HOST 'cd $REMOTE_DIR && docker compose logs bot'"
echo "  telegram       polling"

$SSH "$HOST" "cd $REMOTE_DIR && docker compose logs --tail=200 bot" | grep -qi "conflict" \
  && die "Telegram reports a conflict — something else is still polling this token"
ENTRIES=$($SSH "$HOST" "cd $REMOTE_DIR && docker compose exec -T db psql -U nutrai -d nutrai -t -A -c \
  \"SELECT count(*) FROM log_entry WHERE status='confirmed'\"" | tr -d '\r')
echo "  diary          $ENTRIES confirmed entries"

# --------------------------------------------------------------- backups
say "nightly backup at 03:00 on the server"
$SSH "$HOST" "cd $REMOTE_DIR && chmod +x scripts/backup.sh && \
  ( crontab -l 2>/dev/null | grep -v 'nutrai/scripts/backup.sh' ; \
    echo '0 3 * * * cd $REMOTE_DIR && ./scripts/backup.sh >> /var/log/nutrai-backup.log 2>&1' ) | crontab -"
echo "  cron           installed"

say "done — the bot now runs on $HOST and no longer needs this laptop"
echo "  logs:    ssh $HOST 'cd $REMOTE_DIR && docker compose logs -f bot'"
echo "  psql:    ssh $HOST 'cd $REMOTE_DIR && docker compose exec db psql -U nutrai -d nutrai'"
echo
echo "  This laptop's bot is stopped and must stay stopped: two pollers on one"
echo "  Telegram token fight, and meals land on whichever wins the race."
