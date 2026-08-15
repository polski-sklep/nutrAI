#!/usr/bin/env bash
#
#     scripts/restore.sh nutrai-20260815-193000.sql.gz        # restore for real
#     scripts/restore.sh --check nutrai-20260815-193000.sql.gz  # rehearse only
#
# --check restores into a scratch database, counts the rows, drops it again,
# and touches nothing you own. Run it occasionally. An untested backup is a
# belief, not a backup, and the moment you find out is the worst possible one.
set -euo pipefail

DEST="${NUTRAI_BACKUP_DIR:-$HOME/nutrai-backups}"
CHECK=false
if [[ "${1:-}" == "--check" ]]; then CHECK=true; shift; fi

FILE="${1:-}"
if [[ -z "$FILE" ]]; then
    echo "usage: scripts/restore.sh [--check] <file.sql.gz>" >&2
    ls -1t "$DEST"/nutrai-*.sql.gz 2>/dev/null | head -5 | sed 's/^/  /' >&2
    exit 2
fi
[[ -f "$FILE" ]] || FILE="$DEST/$FILE"
[[ -f "$FILE" ]] || { echo "restore: no such backup: $FILE" >&2; exit 2; }

cd "$(dirname "$0")/.."
gzip -t "$FILE"

if $CHECK; then
    SCRATCH="nutrai_restore_check_$$"
    echo "restore: rehearsing into $SCRATCH (your data is untouched)"
    docker compose exec -T db psql -U nutrai -d postgres -c "CREATE DATABASE $SCRATCH" >/dev/null
    trap 'docker compose exec -T db psql -U nutrai -d postgres -c "DROP DATABASE IF EXISTS '"$SCRATCH"'" >/dev/null 2>&1 || true' EXIT
    gzip -dc "$FILE" | docker compose exec -T db psql -U nutrai -d "$SCRATCH" -q >/dev/null
    docker compose exec -T db psql -U nutrai -d "$SCRATCH" -c \
        "SELECT (SELECT count(*) FROM log_entry) AS entries,
                (SELECT count(*) FROM log_nutrient) AS nutrient_rows,
                (SELECT count(*) FROM target) AS targets,
                (SELECT count(*) FROM food_alias) AS aliases,
                (SELECT count(*) FROM body_metric) AS body_metrics,
                (SELECT count(*) FROM food) AS foods"
    echo "restore: rehearsal succeeded — this backup is restorable"
    exit 0
fi

echo "restore: this REPLACES the current contents of the nutrai database."
read -r -p "type the backup's date (YYYYMMDD) to continue: " confirm
[[ "$FILE" == *"$confirm"* ]] || { echo "restore: no match, nothing done" >&2; exit 1; }

# The dump is taken with --clean --if-exists, so it drops and recreates each
# object as it goes rather than needing the database emptied first.
gzip -dc "$FILE" | docker compose exec -T db psql -U nutrai -d nutrai -q
echo "restore: done. Restart the bot: docker compose up -d bot"
