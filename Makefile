COMPOSE = docker compose --env-file .env.dev
.PHONY: env dev down test check schema admin logs
env:
	python3 scripts/dev-env.py
dev: env
	$(COMPOSE) up --build -d
	@echo "App: http://localhost:8080 | Mail catcher: http://localhost:8025"
down:
	$(COMPOSE) down
test:
	python3 -m unittest discover -s tests -p qms_test.py
	$(COMPOSE) run --rm -e CLINICAL_INTEGRATION_TEST=1 backend pytest
	pnpm test
	python3 tests/database_test.py
check:
	python3 scripts/check_qms.py
	$(COMPOSE) run --rm backend ruff check .
	$(COMPOSE) run --rm backend mypy config identity
	$(COMPOSE) run --rm backend python manage.py makemigrations --check --dry-run
	pnpm lint
	pnpm typecheck
	pnpm build
schema:
	$(COMPOSE) run --rm -v $(CURDIR)/backend:/app backend python manage.py spectacular --file openapi.yaml --validate --fail-on-warn
	pnpm api:types
admin:
	$(COMPOSE) exec backend python manage.py bootstrap_admin $(EMAIL)
logs:
	$(COMPOSE) logs --tail=100 backend worker
