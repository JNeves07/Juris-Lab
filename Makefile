# Atalhos para as tarefas mais comuns do Juris-Lab.
# Uso: make up | make test | make import ...

.PHONY: up down logs test lint import shell-db

# Sobe (ou reconstrói) o banco e a API em segundo plano.
up:
	docker compose up -d --build

# Encerra os serviços (mantém o volume pgdata).
down:
	docker compose down

# Acompanha os logs de todos os serviços.
logs:
	docker compose logs -f

# Executa a suíte de testes do backend.
test:
	cd backend && python -m pytest -q

# Verifica o estilo do código do backend.
lint:
	cd backend && python -m ruff check app importador tests

# Importa as decisões fictícias de exemplo (use --lote/--dry-run se precisar).
import:
	docker compose exec api python -m importador.importar --arquivo /app/dados/exemplo.jsonl --tribunal STJ --fonte "Exemplo (fictício)"

# Abre um psql dentro do container do banco.
shell-db:
	docker compose exec db psql -U juris -d jurisprudencia
