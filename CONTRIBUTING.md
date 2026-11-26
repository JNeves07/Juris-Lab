# Como contribuir

Obrigado por ajudar a melhorar o Juris-Lab! É um projeto de uso pessoal, mas correções, testes e documentação são bem-vindas.

## Preparar o ambiente

O modo padrão é SQLite, então não é preciso banco externo:

```bash
git clone https://github.com/JNeves07/Juris-Lab.git
cd Juris-Lab
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1 | Linux/macOS: source .venv/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cp .env.example .env
make dev
```

Para testar o modo PostgreSQL, use `docker compose --profile postgres up -d --build` e defina `JLS_MODE=postgres` com a `DATABASE_URL` adequada.

## Rodar testes e lint

```bash
python -m ruff check .
cd backend && python -m pytest -q
```

Ou, na raiz: `make check`. A CI repete esses comandos em Python 3.12 e 3.13 e valida também o front-end, os arquivos de configuração, o Compose e o build da imagem. A suíte é offline: novos testes **não devem** exigir rede ou PostgreSQL.

## Estilo

- Siga PEP 8 (o Ruff é a referência) e use nomes e comentários claros.
- Documentação e mensagens voltadas ao usuário em **português**, sem emojis.
- Mantenha as camadas separadas: rotas em `app/routers/`, regras em `services.py`, acesso a dados em `db.py`/`loja.py` e contratos em `schemas.py`.
- Ao escrever SQL, use sempre parâmetros (`%s` ou `%(nome)s`); a camada SQLite traduz automaticamente.
- Escreva testes para toda mudança de comportamento (importador, serviços, API ou loja local).
- **Nunca** comite `.env`, senhas, tokens ou decisões com dados pessoais reais.

## Commits e pull requests

Use prefixos curtos e imperativos: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `ci:` — por exemplo, `docs: explicar sintaxe de busca no README`.

Antes de abrir um PR:

1. testes e lint passando localmente;
2. README atualizado se o comportamento mudou;
3. nenhum segredo ou dado sensível incluído;
4. PR com descrição do problema, da solução e de como testar.

Mudanças em dados jurisprudenciais devem respeitar os termos de uso da fonte oficial e a LGPD.
