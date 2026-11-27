# Juris-Lab

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-integrado-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Vercel](https://img.shields.io/badge/Vercel-serverless-000000?logo=vercel&logoColor=white)](https://vercel.com/)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)](https://github.com/JNeves07/Juris-Lab/actions)

**Seu laboratório pessoal de jurisprudência: busca em português, leitura rastreável e organização própria — funcionando logo após o clone, sem configurar banco.**

---

## Visão geral

Decisões judiciais ficam espalhadas em portais com formatos e filtros incompatíveis. O Juris-Lab reúne em um único lugar:

1. **Busca em linguagem natural em português** com frase exata, `OU`/`OR`, exclusão, ignorando acentos e ordenando por relevância;
2. **Curadoria pessoal**: pastas, tags, favoritos, anotações, relações entre precedentes e controle de vigência;
3. **Rastreabilidade**: cada decisão guarda `fonte`, `fonte_url` e `fonte_id`.

A aplicação roda em dois modos com a **mesma API**:

- `sqlite` (padrão): zero configuração, com 92 tribunais e 5 decisões fictícias carregadas automaticamente. Ideal para desenvolvimento, demonstração, Vercel e uso pessoal.
- `postgres`: PostgreSQL 16 + pgvector, com `COPY` em lotes, índices full-text e esquema preparado para embeddings. Ideal para acervos grandes.

O front-end é HTML, CSS e JavaScript puro, servido pela própria API — sem build, sem framework e sem dependências de node.

## Funcionalidades

- Busca full-text com destaque do trecho (`<mark>`), frase exata, `OU`/`OR`, `-excluir` e metadados (`numero_processo`, CNJ, classe e relator).
- Filtros combináveis: tribunal, ramo, tipo, relator, período, vigência, pasta, tag, favoritos e paginação.
- Acessibilidade: cartões com botões nomeados, diálogos com foco preso e `inert`, paginação com `aria-current`, alertas assertivos e ações destrutivas com desfazer.
- Busca com link permanente: filtros, página e tamanho da página são refletidos na URL; o botão "Copiar link" compartilha o estado exato.
- Exportação dos resultados em CSV (UTF-8 com BOM, delimitador `;`) ou JSON, respeitando os mesmos filtros.
- Leitura completa da decisão com metadados, órgão julgador, anotações, tags, pastas, relações de entrada/saída e histórico.
- Organização pessoal: pastas hierárquicas, tags reutilizáveis, favoritos, anotações com trecho citado, relações tipadas e buscas salvas.
- Importador de JSONL/CSV com mapeamento de colunas, lotes, deduplicação por `hash_conteudo`, `--dry-run` e registro em `coletas`; coletores locais plugáveis com contrato `Coletor`.
- API administrativa com JWT: emissão de token, informações da instância e importação de lote no modo SQLite.
- Docker Compose pronto (SQLite por padrão; PostgreSQL opcional via profile) e deploy serverless na Vercel.
- Documentação OpenAPI em `/api/docs`, healthcheck em `/healthz` e detalhes operacionais em `/api/status`.

## Tecnologias

| Camada | Tecnologia |
| --- | --- |
| Linguagem | Python 3.12 (CI valida 3.12 e 3.13) |
| API | FastAPI + Uvicorn, com Mangum para serverless |
| Validação | Pydantic 2 |
| Banco local | SQLite 3 (camada de compatibilidade SQL em `app/loja.py`) |
| Banco escalável | PostgreSQL 16 + pgvector, psycopg 3 com pool |
| Autenticação | JWT HS256 (PyJWT) |
| Front-end | HTML5, CSS3 e JavaScript puro |
| Testes | pytest (+ httpx/TestClient) |
| Qualidade | Ruff |
| Container | Docker e Docker Compose |
| Deploy | Vercel (`@vercel/python`) e Render (`render.yaml`) |
| Automação | GitHub Actions e Dependabot |

## Arquitetura

```
Front-end (HTML/CSS/JS)
        |
        v
FastAPI  ->  Routers (HTTP)  ->  Services (regras SQL)  ->  db.q()
                                                            |        |
                                                       SQLite     PostgreSQL
                                                      (padrão)    (profile postgres)
```

- `backend/app/routers/`: endpoints de busca, decisões, organização, status e admin.
- `backend/app/services.py`: construção parametrizada das consultas e validações de negócio.
- `backend/app/db.py`: escolhe o backend ativo e expõe `q()`, `abrir()`, `fechar()` e `jsonb()`.
- `backend/app/loja.py`: traduz o SQL PostgreSQL-específico para SQLite e semeia a base de exemplo.
- `backend/app/security.py` e `routers/admin.py`: JWT HS256 e endpoints administrativos.
- `backend/app/schemas.py`: contratos Pydantic de entrada.
- `backend/app/main.py`: fábrica da aplicação, tratamento de erros em português, headers de segurança e estáticos.
- `backend/importador/importar.py`: pipeline de carga isolado da API (`--modo sqlite|postgres`).
- `api/index.py`: entry point da Vercel (`app` ASGI e `handler` Mangum).

A troca de backend é feita apenas por configuração: nenhuma rota muda.

## Início rápido (sem Docker e sem banco externo)

Requer Python 3.12+.

```bash
git clone https://github.com/JNeves07/Juris-Lab.git
cd Juris-Lab
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

O runtime serverless usa `requirements.txt` na raiz; `pyproject.toml` mantém as mesmas dependências para o Vercel e a configuração de Ruff/pytest. Para desenvolvimento, instale os arquivos de `backend/` como no exemplo acima.

Abra <http://localhost:8000>. O banco `data/jurislab.sqlite3` é criado e preenchido na primeira execução. Para usar a raiz do repositório como diretório de trabalho:

```bash
python -m uvicorn app.main:app --app-dir backend --port 8000
```

Também há o atalho `make dev` (raiz do repositório).

## Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

Por padrão sobe somente a API em <http://localhost:8000>, com SQLite persistente no volume `sqlite_data`. Não há dependência de banco externo.

Para usar PostgreSQL/pgvector:

```bash
docker compose --profile postgres up -d --build
```

Nesse modo, `db` fica na porta `5432` e a API conectada ao banco na porta `8001`. Os scripts `db/01_schema.sql` e `db/02_tribunais.sql` são aplicados na primeira inicialização do volume.

Comandos úteis: `make up`, `make down`, `make logs`, `make postgres`, `make shell-db`.

## Vercel

Deploy em produção: <https://juris-lab-beryl.vercel.app> (espelho da equipe: <https://juris-lab-marcelejoao7-9881.vercel.app>).
Healthcheck: `/healthz` e status da instância: `/api/status`.

O `vercel.json` já aponta para `api/index.py`. Na Vercel:

1. *Add New... -> Project* e importe `JNeves07/Juris-Lab`;
2. Framework: **Other**; runtime Python 3.12;
3. Variáveis de ambiente:

| Variável | Valor sugerido |
| --- | --- |
| `JLS_MODE` | `sqlite` |
| `JLS_JWT_SECRET` | valor aleatório longo (32+ caracteres) |
| `JLS_ADMIN_PASSWORD` | senha forte |

Na Vercel o banco é em memória (`VERCEL=1`) e semeado a cada cold start: a instância serve para demonstração e leitura. Para persistência, use PostgreSQL externo com `JLS_MODE=postgres` e `DATABASE_URL`.

Como alternativa, `render.yaml` descreve o mesmo serviço no Render com `--app-dir backend`.

## Configuração

Todas as opções vêm de variáveis de ambiente. **Nunca versionar `.env`, tokens ou dados reais.**

| Variável | Padrão | Uso |
| --- | --- | --- |
| `JLS_MODE` | `sqlite` (ou `postgres` se `DATABASE_URL` existir) | Backend ativo. |
| `JLS_DB_PATH` | `data/jurislab.sqlite3` (`:memory:` na Vercel) | Arquivo do SQLite. |
| `JLS_SEED` | `1` | Carrega tribunais e decisões fictícias se a base estiver vazia. |
| `JLS_JWT_SECRET` | `dev-only-jurislab-change-me-in-production` | Chave de assinatura do JWT. Troque em produção. |
| `JLS_ADMIN_PASSWORD` | `admin` | Senha de `POST /api/admin/token`. Troque em produção. |
| `JLS_CORS_ORIGINS` | vazio | Origens permitidas separadas por vírgula; vazio = mesma origem. |
| `JLS_RATE_LIMIT` / `JLS_RATE_WINDOW` | `10` / `60` | Limite de tentativas de token por IP e janela em segundos. |
| `JLS_TRUST_PROXY` | `0` | Confia em `X-Forwarded-For`; use `1` apenas atrás de proxy conhecido. |
| `JLS_REQUEST_ID` | `0` | Inclui `X-Request-ID` nas respostas. |
| `JLS_ALLOW_DEFAULT_SECRETS` | `0` | Autoriza segredos de desenvolvimento apenas em demonstrações e testes. |
| `DATABASE_URL` | `postgresql://juris:juris_dev@localhost:5432/jurisprudencia` | Conexão usada no modo `postgres`. |
| `FRONTEND_DIR` | `<raiz>/frontend` | Diretório servido em `/` e `/static`. |
| `LIMITE_CONTAGEM` | `10000` | Teto da contagem de resultados. |
| `JLS_EXPORT_MAX` | `1000` | Máximo de decisões por exportação. |
| `LOG_LEVEL` | `info` | Nível de log (`debug`, `info`, `warning`, `error`). |

## Uso da API

Documentação interativa: <http://localhost:8000/api/docs>. Exemplos:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/api/status

curl -G http://localhost:8000/api/busca \
  --data-urlencode 'q="dano moral" OU responsabilidade -prescrição' \
  --data-urlencode 'tribunal=STJ' \
  --data-urlencode 'ordem=relevancia' \
  --data-urlencode 'pagina=1' \
  --data-urlencode 'por_pagina=20'

curl -G http://localhost:8000/api/busca/export \
  --data-urlencode 'q=dano moral' \
  --data-urlencode 'formato=csv' -o jurislab.csv

curl -G http://localhost:8000/api/busca/export \
  --data-urlencode 'status=vigente' \
  --data-urlencode 'formato=json' -o jurislab.json

curl http://localhost:8000/api/tribunais
curl http://localhost:8000/api/estatisticas
curl http://localhost:8000/api/decisoes/1

curl -X PUT http://localhost:8000/api/decisoes/1/favorito
curl -X PUT http://localhost:8000/api/decisoes/1/status \
  -H 'Content-Type: application/json' -d '{"status":"superada"}'

curl -X POST http://localhost:8000/api/pastas \
  -H 'Content-Type: application/json' -d '{"nome":"Responsabilidade Civil"}'
curl -X PUT http://localhost:8000/api/decisoes/1/tags \
  -H 'Content-Type: application/json' -d '{"nome":"importante"}'
curl -X POST http://localhost:8000/api/decisoes/1/anotacoes \
  -H 'Content-Type: application/json' -d '{"texto":"Revisar entendimento","trecho":"..."}'
curl -X POST http://localhost:8000/api/decisoes/1/relacoes \
  -H 'Content-Type: application/json' \
  -d '{"destino_id":2,"tipo":"distingue","nota":"Contexto factual diverso"}'
```

### Administração (JWT)

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/admin/token \
  -H 'Content-Type: application/json' \
  -d '{"password":"admin"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/info

curl -X POST http://localhost:8000/api/admin/importar \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"tribunal":"STJ","fonte":"Importação pela API","registros":[{"fonte_id":"NOVO-1","ementa":"Decisão sobre dano moral","tipo":"acordao"}]}'
```

O exemplo usa os valores de desenvolvimento: para que o token seja emitido, defina `JLS_ALLOW_DEFAULT_SECRETS=1`. Em produção, use segredos próprios e remova essa variável.

A importação pela API está disponível no modo SQLite. No PostgreSQL use a CLI do importador.

## Sintaxe de busca

| Sintaxe | Exemplo | Resultado |
| --- | --- | --- |
| Termos livres | `dano moral consumidor` | todos os termos (AND implícito) |
| Frase exata | `"dano moral"` | termos próximos, na ordem |
| Alternativa | `dano OU prejuízo` | qualquer termo (`OR` também funciona) |
| Exclusão | `dano -prescrição` | remove decisões com o termo excluído |
| Combinação | `"frase exata" OU termo -excluir` | combinação das regras acima |

No PostgreSQL a busca usa `websearch_to_tsquery` com `pt_unaccent` (ignora acentos e flexões, com ranqueamento por relevância). No SQLite a camada de compatibilidade implementa uma aproximação determinística: corresponder substrings, ignorar acentos e caixa e pontuar termos da consulta; não há stemming nem ranqueamento `ts_rank_cd` completo. Metadados também são pesquisados por `numero_processo`, `numero_cnj`, `classe` e `relator`. A contagem para em 10.000 (`total_truncado: true`) para manter a resposta rápida.

## Importação de dados

JSONL (uma decisão por linha) ou CSV com cabeçalho. Campos: `fonte_id`, `ementa`, `numero_processo`, `classe`, `relator`, `orgao_julgador`, `tipo`, `data_julgamento`, `data_publicacao`, `inteiro_teor`, `tese`, `legislacao_citada`, `fonte_url`. `fonte_id` e pelo menos um texto são obrigatórios.

```bash
# SQLite local (padrão)
python -m importador.importar --arquivo ../dados/exemplo.jsonl \
  --tribunal STJ --fonte "Exemplo (fictício)" --modo sqlite

# PostgreSQL (dentro do container ou com DATABASE_URL apontando para ele)
python -m importador.importar --arquivo dados/exemplo.jsonl \
  --tribunal STJ --fonte "Exemplo (fictício)" --modo postgres

# Simulação, sem gravar
python -m importador.importar --arquivo dados/exemplo.jsonl \
  --tribunal STJ --fonte "Teste" --dry-run
```

`--mapa` traduz nomes de colunas da fonte (`{"fonte_id": "id_documento", ...}`) e `--lote` controla o tamanho do lote no PostgreSQL. Linhas inválidas são ignoradas e contabilizadas; cada execução fica registrada em `coletas`.

Coletores locais são classes com `coletar() -> dict` e `fechar()`. O coletor JSONL incluído (`backend/importador/coletores/jsonl.py`) lê um arquivo ou a entrada padrão; `--coletor jsonl --origem -` permite encadear outro coletor pelo pipe:

```bash
type dados\exemplo.jsonl | python -m importador.importar --coletor jsonl --origem - \
  --tribunal STJ --fonte "Exemplo (fictício)" --modo sqlite
```

`dados/coletores.exemplo.json` documenta o contrato. Coletores http não são incluídos: a coleta deve respeitar a fonte oficial e seus termos de uso.

## Testes e qualidade

A suíte é totalmente offline (sem rede e sem PostgreSQL): 123 testes cobrem serviços, importador e coletores, validações, configuração, limites, API com dublês, SQLite real, JWT/admin e entry point da Vercel.

```bash
# A partir da raiz
python -m ruff check .
cd backend && python -m pytest -q

# Ou com os atalhos
make check
```

## Integração contínua

`.github/workflows/ci.yml` executa em push/PR para `main`:

- `quality`: matriz Python 3.12/3.13 com Ruff e pytest;
- `artefatos`: `node --check` do front-end, validação de JSON/YAML, `docker compose config -q` e build da imagem.

O Dependabot abre PRs semanais para pip, GitHub Actions e Dockerfile.

## Estrutura

```
Juris-Lab/
├── README.md                    # este documento
├── CONTRIBUTING.md
├── Makefile
├── requirements.txt             # dependências do runtime @vercel/python
├── pyproject.toml               # metadados, dependências e configuração do Ruff/pytest
├── docker-compose.yml           # API SQLite + perfil opcional postgres
├── vercel.json / render.yaml    # deploy serverless
├── .env.example
├── .github/
│   ├── workflows/ci.yml
│   └── dependabot.yml
├── api/index.py                 # entry point Vercel (Mangum)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt / requirements-dev.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── config.py / db.py / loja.py
│   │   ├── security.py / schemas.py / services.py / main.py
│   │   └── routers/{status,busca,decisoes,organizacao,admin}.py
│   ├── importador/
│   │   ├── importar.py
│   │   └── coletores/{__init__,base,jsonl,mapeador}.py
│   └── tests/
├── frontend/
│   ├── index.html
│   ├── css/styles.css
│   ├── js/app.js
│   └── assets/
├── data/                        # SQLite gerado localmente (ignorado no git)
├── dados/exemplo.jsonl          # decisões fictícias
├── dados/coletores.exemplo.json # contrato de um coletor local
├── db/01_schema.sql / 02_tribunais.sql
└── docs/original/               # projeto original preservado
```

## Fontes oficiais

Use canais oficiais e respeite os termos de uso: STJ (dados abertos), STF (dados abertos), DataJud/CNJ (metadados processuais, sem inteiro teor) e portais dos tribunais estaduais/federais. Registre sempre `fonte`, `fonte_url` e `fonte_id`.

## Avisos importantes

- **LGPD**: decisões podem conter dados pessoais. Mantenha o acervo em ambiente confiável, proteja credenciais e nunca publique o banco sem avaliação jurídica e de privacidade.
- **Confira a fonte oficial**: a ferramenta organiza e pesquisa, mas não substitui a consulta no site do tribunal antes de citar uma decisão.
- **Vigência é curadoria**: `status` é manual, não automático.
- Registros em `dados/exemplo.jsonl` são fictícios e servem apenas para teste.
- Em produção, troque `JLS_JWT_SECRET` e `JLS_ADMIN_PASSWORD`. Com valores padrão, a emissão/validação de JWT exige `JLS_ALLOW_DEFAULT_SECRETS=1` e `/api/status` sinaliza `segredos_padrao: true`.

## Próximos passos

1. embeddings com pgvector e índice HNSW para busca semântica;
2. alertas de mudança usando `buscas_salvas` + `historico_alteracoes`;
3. coletores oficiais por tribunal gerando JSONL padronizado (o contrato local já está disponível);
4. resumo assistido por IA com revisão humana obrigatória;
5. migração da indexação para OpenSearch/Meilisearch em acervos muito grandes.

O projeto original está preservado em [`docs/original/`](docs/original/) para referência.

## Licença

Ferramenta de uso pessoal e estudo. Verifique a licença dos dados de cada tribunal antes de redistribuí-los.
