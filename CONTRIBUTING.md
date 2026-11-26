# Como contribuir

Obrigado por ajudar a melhorar o Juris-Lab! Este é um projeto de uso pessoal, mas qualquer correção, teste ou documentação é bem-vinda.

## Preparar o ambiente

```bash
cp .env.example .env
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1 | Linux/macOS: source .venv/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
```

Para subir o banco e a API com Docker: `docker compose up -d --build`.

## Rodar testes e lint

```bash
cd backend
python -m pytest -q
python -m ruff check app importador tests
```

Ou, na raiz do repositório: `make test` e `make lint`. A CI repete exatamente esses comandos em Python 3.12 e 3.13 e também valida o Compose com `docker compose config`.

## Estilo

- Siga PEP 8 (o Ruff é a referência) e use nomes e comentários claros.
- Documentação e mensagens voltadas ao usuário em **português**.
- Mantenha as camadas separadas: rotas em `app/routers/`, regras em `services.py`, SQL em `db.py` e contratos em `schemas.py`.
- Escreva testes para toda mudança de comportamento (importador, serviços ou API).
- **Nunca** comite `.env`, senhas, tokens ou decisões com dados pessoais reais.

## Commits e pull requests

Use prefixos curtos e imperativos: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `ci:` — por exemplo, `docs: explicar sintaxe de busca no README`.

Antes de abrir um PR:

1. testes e lint passando localmente;
2. README atualizado se o comportamento mudou;
3. nenhum segredo ou dado sensível incluído;
4. PR com descrição do problema, da solução e de como testar.

Mudanças em dados jurisprudenciais devem respeitar os termos de uso da fonte oficial e a LGPD.
