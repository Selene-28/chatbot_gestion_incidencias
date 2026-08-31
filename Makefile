# Chatbot CTIC-FIIS UNAC — tareas comunes de desarrollo

SERVICES := services/chatbot-api services/ticket-service

.PHONY: up down logs ps test lint reset-db

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

test:
	@for svc in $(SERVICES); do \
		echo "==> pytest en $$svc"; \
		(cd $$svc && uv run pytest) || exit 1; \
	done

lint:
	@for svc in $(SERVICES); do \
		echo "==> ruff en $$svc"; \
		(cd $$svc && uv run ruff check .) || exit 1; \
	done

reset-db:
	docker compose down -v
	docker compose up -d --build
