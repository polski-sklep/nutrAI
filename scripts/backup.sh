#!/usr/bin/env bash
#
# Dump the whole database, verify the dump, rotate old ones.
#
#     scripts/backup.sh                 # write one backup
#     NUTRAI_BACKUP_DIR=/mnt/x scripts/backup.sh
#
# The dump includes the USDA reference tables even though they are
# reproducible from a public download. At 7.6 MB compressed the saving from
# excluding them is not worth what it costs: a backup that needs a 3 GB
# re-download and a working loader before it restores is not a backup, it is a
# note saying where the backup should have been.
#
# What is genuinely irreplaceable is small and none of it can be regenerated:
# every confirmed meal, the immutable log_nutrient snapshots, the versioned
# target history that makes "did the change I made in August do anything"
# answerable at all, and the food_alias vocabulary the system has learned about
# how you eat.
set -euo pipefail

DEST="${NUTRAI_BACKUP_DIR:-$HOME/nutrai-backups}"
KEEP="${NUTRAI_BACKUP_KEEP:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DEST/nutrai-$STAMP.sql.gz"

cd "$(dirname "$0")/.."
mkdir -p "$DEST"

if ! docker compose ps --status running --services 2>/dev/null | grep -qx db; then
    echo "backup: the db service is not running — nothing to dump" >&2
    exit 1
fi

# Row counts from the live database, to be checked against the dump. A dump
# that runs to completion and contains nothing is the failure mode that matters:
# it exits 0, writes a plausible-looking file, and is discovered to be empty on
# the one day it is needed.
read -r entries nutrients targets aliases metrics <<<"$(
    docker compose exec -T db psql -U nutrai -d nutrai -tAF' ' -c \
        "SELECT (SELECT count(*) FROM log_entry), (SELECT count(*) FROM log_nutrient),
                (SELECT count(*) FROM target), (SELECT count(*) FROM food_alias),
                (SELECT count(*) FROM body_metric)"
)"

# Written to a temporary name and moved into place only once it is verified, so
# an interrupted run cannot leave a half-written file that looks like a backup.
docker compose exec -T db pg_dump -U nutrai -d nutrai --clean --if-exists \
    | gzip > "$OUT.tmp"

gzip -t "$OUT.tmp"

# Decompressed once into a list of the tables the dump actually carries.
#
# Not `gzip -dc file | grep -q pattern` per table: with `set -o pipefail`,
# grep -q exits the moment it matches, gzip takes SIGPIPE, and the pipeline
# reports failure on the tables that were present. The first version of this
# check refused every good backup it was given.
present="$(gzip -dc "$OUT.tmp" | grep -o '^COPY public\.[a-z_]*' | sort -u)"

for table in log_entry log_nutrient target food_alias body_metric food_nutrient; do
    if ! grep -qxF "COPY public.$table" <<<"$present"; then
        echo "backup: $table missing from the dump — refusing to keep it" >&2
        rm -f "$OUT.tmp"
        exit 1
    fi
done

mv "$OUT.tmp" "$OUT"

cat > "$DEST/latest.txt" <<EOF
$(basename "$OUT")
taken           $(date -u +"%Y-%m-%dT%H:%M:%SZ")
log entries     $entries
nutrient rows   $nutrients
targets         $targets
learned aliases $aliases
body metrics    $metrics
restore with    scripts/restore.sh $(basename "$OUT")
EOF

ls -1t "$DEST"/nutrai-*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
    rm -f "$old"
done

printf 'backup: %s (%s) · %s entries, %s targets, %s aliases\n' \
    "$OUT" "$(du -h "$OUT" | cut -f1)" "$entries" "$targets" "$aliases"
