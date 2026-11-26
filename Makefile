# Atalhos para as tarefas mais comuns do Juris-Lab.
# Uso: make dev | make up | make test | make import ...

.PHONY: dev up down logs postgres test lint check import import-pg shell-db

# Roda a API localmente com SQLite e dados de exemplo (sem Docker).
dev:
	cd backend && python -m uvicorn app.main:app --reload --port 8000

# Sobe a API pronta para uso (SQLite) em segundo plano.
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

# Sobe PostgreSQL/pgvector e a API conectada a ele na porta 8001.
postgres:
	docker compose --profile postgres up -d --build

# Executa a suíte de testes (sem banco externo).
test:
	cd backend && python -m pytest -q

# Verifica o estilo do código.
lint:
	python -m ruff check .

# Testes + lint.
check: test lint

# Importa as decisões fictícias no SQLite local.
import:
	cd backend && python -m importador.importar --arquivo ../dados/exemplo.jsonl --tribunal STJ --fonte "Exemplo (fictício)" --modo sqlite

# Importa no PostgreSQL (com o profile `postgres` ativo).
import-pg:
	docker compose --profile postgres exec api-postgres python -m importador.importar --arquivo /app/dados/exemplo.jsonl --tribunal STJ --fonte "Exemplo (fictício)"

# Abre um psql dentro do container do banco.
shell-db:
	docker compose --profile postgres exec db psql -U juris -d jurisprudencia
