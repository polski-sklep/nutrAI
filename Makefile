.PHONY: db test load bootstrap pin run logs deploy fmt backup backup-check

db:                       ## Postgres only; schema in sql/ applies on first boot
	docker compose up -d db

test:                     ## 60 tests, no database required
	pytest -q

load:                     ## make load FDC=~/Downloads/FoodData_Central_csv_2025-04-24
	python scripts/load_usda.py $(FDC)

bootstrap:                ## make bootstrap ID=123456789
	python scripts/bootstrap.py --telegram-id $(ID) --sex male --age 34 \
		--height-cm 183 --weight-kg 74.4 --activity 1.55 --deficit 500 --protein-g 180

pin:                      ## make pin ID=123456789
	python scripts/pin_foods.py --telegram-id $(ID) --pin

run:                      ## run the bot locally against the local db
	python -m nutrai.bot

logs:
	docker compose logs -f bot

backup:                   ## dump, verify and rotate. NUTRAI_BACKUP_DIR to relocate
	./scripts/backup.sh

backup-check:             ## rehearse the latest restore into a scratch db
	./scripts/restore.sh --check $$(ls -1t $${NUTRAI_BACKUP_DIR:-$$HOME/nutrai-backups}/nutrai-*.sql.gz | head -1)

deploy:                   ## on the VPS: pull, rebuild, restart. DB untouched.
	git pull --ff-only
	docker compose build bot
	docker compose up -d bot
	docker compose logs --tail=40 bot

fmt:
	ruff check --fix nutrai scripts tests && ruff format nutrai scripts tests
