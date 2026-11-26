# Juris-Lab

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)](https://docs.github.com/actions)

**Seu laboratório pessoal de jurisprudência: busca rápida em português, organização própria e rastreabilidade da fonte oficial.**

---

## O problema

Decisões judiciais estão espalhadas em portais diferentes, com formatos, vocabulários e filtros incompatíveis. Quem pesquisa jurisprudência todo dia precisa de três coisas que os buscadores genéricos não entregam bem:

1. **Busca em linguagem natural em português**, com frase exata, `OR` e exclusão, que ignore acentos e ordene por relevância jurídica (ementa > tese > inteiro teor).
2. **Escala**: um acervo com milhões de decisões em um único banco, sem custo de infraestrutura de busca externa.
3. **Curadoria pessoal**: pastas, tags, favoritos, anotações, relações entre precedentes e controle de vigência — sem depender de um serviço de terceiros.

O Juris-Lab resolve isso com um PostgreSQL 16 + pgvector, uma API FastAPI enxuta e uma interface web em HTML/CSS/JS puro, servida pela própria API. Tudo pode rodar na sua máquina com `docker compose up`.

## Funcionalidades

- **Busca full-text** com `websearch_to_tsquery` e configuração `pt_unaccent`: `"frase exata"`, `termo1 OR termo2`, `-excluir`, ordenação por relevância ou data e destaque do trecho encontrado.
- **Filtros combináveis**: tribunal, ramo, tipo de decisão, relator, período, vigência, pasta, tag, favoritos e paginação.
- **Leitura completa** da decisão com metadados, órgão julgador, anotações, tags, pastas, relações e histórico de alterações.
- **Importação em massa** de JSONL ou CSV, com mapeamento de colunas (`--mapa`), lotes configuráveis (`--lote`) e simulação sem gravar (`--dry-run`).
- **Deduplicação e histórico**: chave `(tribunal, fonte_id)`, `hash_conteudo` para atualizar só quando o texto muda e registro automático de alterações de ementa/tese/vigência.
- **Organização pessoal**: pastas hierárquicas, tags, favoritos, anotações (com trecho citado), relações entre decisões e buscas salvas.
- **Controle de vigência** manual (`vigente` / `superada`) por decisão.
- **Painel de estatísticas** e cadastro de tribunais carregado na primeira subida do banco.
- **Interface web leve** em `/` e arquivos estáticos em `/static`, sem framework de front-end.
- **Pronto para busca semântica**: tabela de embeddings com pgvector já prevista no esquema (geração dos vetores e índice HNSW são próximos passos).

## Tecnologias

| Camada | Tecnologia |
| --- | --- |
| Linguagem | Python 3.12 (CI também valida 3.13) |
| API | FastAPI + Uvicorn |
| Validação | Pydantic 2 |
| Acesso a dados | psycopg 3 (com pool) e SQL puro |
| Banco | PostgreSQL 16 + extensão pgvector |
| Front-end | HTML5, CSS3 e JavaScript puro |
| Testes | pytest |
| Qualidade | Ruff |
| Container | Docker e Docker Compose |
| Automação | GitHub Actions e Dependabot |

## Arquitetura em camadas

As responsabilidades ficam separadas para facilitar testes e manutenção:

```
Router (HTTP)  →  Service (regras de negócio)  →  DB (SQL/psycopg)  →  PostgreSQL
     ↑                      ↑                          ↑
  schemas.py            services.py                config.py
  (Pydantic)           (regras/organização)     (variáveis de ambiente)
```

- `app/routers/`: endpoints da API (busca, decisões, organização) — apenas HTTP e validação de entrada.
- `app/services.py`: regras de negócio e orquestração das consultas.
- `app/db.py`: pool de conexões e acesso ao banco.
- `app/schemas.py`: contratos Pydantic de entrada e saída.
- `app/config.py`: leitura centralizada de configuração (`.env`).
- `app/main.py`: criação da aplicação, healthz e montagem do front-end estático.
- `importador/importar.py`: pipeline de carga em lotes, isolado da API.

## Pré-requisitos

**Para Docker (recomendado):**
- Docker Engine 24+ com o plugin Compose v2 (`docker compose version`).

**Para execução local:**
- Python 3.12 ou 3.13.
- PostgreSQL 16 com a extensão `vector` (pgvector) disponível.
- `git` e um terminal (PowerShell, bash ou equivalente).

## Instalação

### 1. Com Docker Compose

```bash
git clone https://github.com/JNeves07/Juris-Lab.git
cd Juris-Lab
cp .env.example .env
docker compose up -d --build
```

Na primeira subida, os scripts `db/01_schema.sql` e `db/02_tribunais.sql` criam as tabelas e cadastram os tribunais. A API fica em <http://localhost:8000>, a documentação interativa em <http://localhost:8000/docs> e o banco na porta `5432`.

### 2. Local, com ambiente virtual

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/macOS
python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cp .env.example .env
```

Suba apenas o banco com Docker e aponte a conexão para `localhost`:

```bash
docker compose up -d db
# Ajuste DATABASE_URL no .env para:
# postgresql://juris:juris_dev@localhost:5432/jurisprudencia
```

Inicie a API:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> Ao executar localmente, `FRONTEND_DIR` pode apontar para a pasta `frontend` do repositório; dentro do container o valor padrão é `/app/frontend`.

## Configuração

Todas as configurações vêm de variáveis de ambiente carregadas do `.env` (copie `.env.example`). **Nunca versionar o `.env` nem senhas reais.**

| Variável | Valor de exemplo | Uso |
| --- | --- | --- |
| `DB_PASSWORD` | `juris_dev` | Senha do usuário `juris` no PostgreSQL do Compose. |
| `DATABASE_URL` | `postgresql://juris:juris_dev@db:5432/jurisprudencia` | String de conexão usada pela API e pelo importador (use `localhost` fora do Compose). |
| `FRONTEND_DIR` | `/app/frontend` | Diretório dos arquivos estáticos servidos em `/` e `/static`. |
| `LOG_LEVEL` | `info` | Nível de log da aplicação. |

## Subindo e verificando

```bash
docker compose up -d --build     # sobe db + api
docker compose logs -f api       # acompanha a API
docker compose ps                # status dos serviços
curl http://localhost:8000/healthz
```

O healthcheck da API consulta `/healthz`; o do banco usa `pg_isready`. A API só é considerada pronta quando o banco estiver saudável (`depends_on: service_healthy`).

## Importação de dados

O importador aceita **JSONL** (uma decisão por linha) e **CSV** (com cabeçalho). Campos reconhecidos: `fonte_id`, `numero_processo`, `classe`, `relator`, `orgao_julgador`, `tipo`, `data_julgamento`, `data_publicacao`, `ementa`, `inteiro_teor`, `tese`, `legislacao_citada`, `fonte_url`. `fonte_id` e pelo menos um texto (ementa ou inteiro teor) são obrigatórios.

O repositório traz `dados/exemplo.jsonl` com decisões **fictícias**, apenas para validar o fluxo:

```bash
# Simulação: não grava nada no banco
docker compose exec api python -m importador.importar \
  --arquivo /app/dados/exemplo.jsonl \
  --tribunal STJ \
  --fonte "Exemplo (fictício)" \
  --lote 5000 \
  --dry-run

# Carga real
docker compose exec api python -m importador.importar \
  --arquivo /app/dados/exemplo.jsonl \
  --tribunal STJ \
  --fonte "Exemplo (fictício)"
```

Para remover os dados de exemplo depois do teste:

```bash
docker compose exec db psql -U juris -d jurisprudencia \
  -c "DELETE FROM decisoes WHERE fonte = 'Exemplo (fictício)';"
```

### Mapeando colunas (`--mapa`)

Quando o arquivo da fonte usa outros nomes, forneça um JSON com `{campo_do_banco: coluna_do_arquivo}`:

```json
{
  "fonte_id": "id_documento",
  "ementa": "ementa",
  "numero_processo": "processo",
  "relator": "ministro_relator",
  "data_julgamento": "dt_julgamento",
  "inteiro_teor": "texto_integral",
  "orgao_julgador": "orgao"
}
```

```bash
docker compose exec api python -m importador.importar \
  --arquivo /app/dados/stj_2024.csv \
  --tribunal STJ \
  --fonte "STJ dados abertos" \
  --mapa /app/dados/mapa_stj.json \
  --lote 10000
```

- `--lote` controla quantos registros são enviados por `COPY` em cada transação (padrão: 5.000).
- `--dry-run` valida, normaliza e mostra o que seria feito sem gravar no banco.
- Consulte `python -m importador.importar --help` para a lista completa de opções.

Cada execução fica registrada em `coletas`. Linhas inválidas são ignoradas e contabilizadas; registros idênticos aos existentes não são reescritos.

## Endpoints (exemplos com curl)

```bash
# Saúde da aplicação
curl http://localhost:8000/healthz

# Busca com frase exata, filtro de tribunal e paginação
curl -G http://localhost:8000/api/busca \
  --data-urlencode 'q="responsabilidade objetiva" OR "dano moral" -prescrição' \
  --data-urlencode 'tribunal=STJ' \
  --data-urlencode 'ordem=relevancia' \
  --data-urlencode 'pagina=1' \
  --data-urlencode 'por_pagina=20'

# Tribunais cadastrados e estatísticas gerais
curl http://localhost:8000/api/tribunais
curl http://localhost:8000/api/estatisticas

# Decisão específica (inclui anotações, tags, pastas, relações e histórico)
curl http://localhost:8000/api/decisoes/1

# Organização pessoal
curl http://localhost:8000/api/pastas
curl http://localhost:8000/api/tags
curl http://localhost:8000/api/buscas-salvas

# Favoritar e alterar vigência
curl -X PUT http://localhost:8000/api/decisoes/1/favorito
curl -X PUT http://localhost:8000/api/decisoes/1/status \
  -H 'Content-Type: application/json' \
  -d '{"status": "superada"}'

# Criar pasta, tag, anotação e relação
curl -X POST http://localhost:8000/api/pastas \
  -H 'Content-Type: application/json' -d '{"nome": "Responsabilidade Civil"}'
curl -X PUT http://localhost:8000/api/decisoes/1/tags \
  -H 'Content-Type: application/json' -d '{"nome": "dano moral"}'
curl -X POST http://localhost:8000/api/decisoes/1/anotacoes \
  -H 'Content-Type: application/json' -d '{"texto": "Entendimento revisado em 2024.", "trecho": "..."}'
curl -X POST http://localhost:8000/api/decisoes/1/relacoes \
  -H 'Content-Type: application/json' \
  -d '{"destino_id": 2, "tipo": "distingue", "nota": "Contexto factual diverso"}'
```

A documentação OpenAPI/Swagger está disponível em <http://localhost:8000/docs>.

## Sintaxe de busca

A busca usa `websearch_to_tsquery` com o dicionário `pt_unaccent`, então `contrato` encontra `contratual` e `ação` encontra `acao`:

| Sintaxe | Exemplo | Resultado |
| --- | --- | --- |
| Termos livres | `dano moral consumidor` | todos os termos (AND implícito) |
| Frase exata | `"dano moral"` | termos adjacentes, na ordem |
| Alternativa | `dano OR prejuízo` | qualquer um dos termos |
| Exclusão | `dano -prescrição` | remove decisões com o termo excluído |
| Combinação | `"frase exata" OR termo -excluir` | combinações das regras acima |

Ordenação por relevância pondera mais a ementa, depois a tese e por fim o inteiro teor. A contagem para em 10.000 resultados (`total_truncado: true`) para manter a resposta rápida mesmo com milhões de decisões.

## Organização pessoal

- **Pastas**: hierárquicas (`pai_id`), com contagem de decisões; uma decisão pode estar em várias pastas.
- **Tags**: normalizadas em minúsculas, reutilizadas entre decisões.
- **Favoritos**: marcação rápida com filtro dedicado na busca (`favoritos=true`).
- **Anotações**: texto livre com trecho opcional da decisão e data de criação.
- **Relações**: vínculos entre precedentes (`origem → destino`) com tipo e nota; a leitura mostra relações de entrada e saída.
- **Vigência**: `status` manual (`vigente` / `superada`), registrado no histórico de alterações.
- **Buscas salvas**: nome, consulta e filtros em JSONB, prontos para alimentar alertas.

Tudo isso é de uso pessoal: não altera o texto original da decisão, apenas acrescenta metadados locais.

## Testes e qualidade

```bash
# Na pasta backend/
python -m pytest -q
python -m ruff check app importador tests
```

Ou, a partir da raiz, com `make test` e `make lint`. Os testes cobrem o importador (`test_importador.py`), as regras de serviço (`test_services.py`) e a API (`test_api.py`).

## Integração contínua

O workflow `.github/workflows/ci.yml` executa, em cada push e pull request:

- **job `backend`**: matriz Python 3.12 e 3.13, instalação de `requirements.txt` + `requirements-dev.txt`, `python -m pytest -q` e `python -m ruff check app importador tests` (com `working-directory: backend`).
- **job `compose`**: validação do arquivo do Compose com `docker compose config`.

O `.github/dependabot.yml` abre PRs semanais de atualização para `pip` (em `/backend`) e `github-actions`.

## Estrutura de pastas

```
Juris-Lab/
├── README.md                    # este documento
├── CONTRIBUTING.md              # como contribuir
├── Makefile                     # atalhos: up, down, logs, test, lint, import, shell-db
├── docker-compose.yml           # serviços db + api
├── .env.example                 # modelos de variáveis (sem segredos reais)
├── .gitignore / .dockerignore
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── schemas.py
│   │   ├── services.py
│   │   ├── main.py
│   │   └── routers/
│   │       ├── busca.py
│   │       ├── decisoes.py
│   │       └── organizacao.py
│   ├── importador/
│   │   └── importar.py
│   └── tests/
│       ├── test_importador.py
│       ├── test_services.py
│       └── test_api.py
├── frontend/
│   ├── index.html
│   ├── css/styles.css
│   ├── js/app.js
│   └── assets/favicon.svg
├── dados/
│   └── exemplo.jsonl            # decisões fictícias para teste
├── db/
│   ├── 01_schema.sql
│   └── 02_tribunais.sql
├── docs/
│   └── original/                # projeto original preservado (não usar em produção)
└── .github/
    ├── workflows/ci.yml
    └── dependabot.yml
```

## Fontes oficiais de dados

Use preferencialmente canais oficiais e respeite os termos de uso de cada fonte:

- **STJ** — portal de dados abertos e portal de jurisprudência do Superior Tribunal de Justiça.
- **STF** — portal de dados abertos e buscas oficiais do Supremo Tribunal Federal.
- **DataJud (CNJ)** — API de metadados processuais; **não fornece o inteiro teor**, portanto é útil para localizar processos, não para substituir a leitura da decisão.
- **Portais de jurisprudência dos tribunais estaduais e federais** — verifique se autorizam coleta automatizada antes de criar um coletor.

Registre sempre `fonte`, `fonte_url` e `fonte_id` para saber de onde veio cada decisão.

## Avisos importantes

- **LGPD**: decisões judiciais podem conter dados pessoais (nomes, CPF, endereços, processos sigilosos). Mantenha o acervo apenas na sua máquina ou rede confiável, proteja o `.env` e as credenciais, defina política de retenção e nunca publique o banco sem avaliação jurídica e de privacidade.
- **Confira a fonte oficial**: esta ferramenta organiza e pesquisa; **não substitui a consulta da decisão no site do tribunal antes de citá-la**. Ementas e teses podem ter sido alteradas ou revogadas.
- **Vigência é curadoria**: o campo `status` é manual (ou depende dos seus coletores); não presuma que ele reflete automaticamente a situação processual real.
- Os registros em `dados/exemplo.jsonl` são **fictícios** e existem apenas para testar a importação.

## Próximos passos

1. **Embeddings com pgvector**: gerar vetores das ementas/teses e criar índice HNSW para busca semântica combinada com a busca textual.
2. **Alertas de mudança de entendimento**: usar `buscas_salvas` + `historico_alteracoes` para avisar quando uma decisão monitorada muda.
3. **Coletores por tribunal**: um adaptador por fonte oficial que baixa os dados e gera o JSONL padronizado.
4. **Resumo assistido por IA** com revisão humana obrigatória (risco de alucinação em texto jurídico).
5. **Escalabilidade**: se o acervo passar de dezenas de milhões de decisões ou a busca ficar lenta, migrar a indexação para OpenSearch/Meilisearch mantendo o PostgreSQL como fonte da verdade.

O projeto original está preservado em [`docs/original/`](docs/original/) (incluindo o README e o arquivo histórico) para referência; o código ativo é o descrito acima.

## Licença e uso

Ferramenta de uso pessoal e estudo. Verifique a licença dos dados obtidos de cada tribunal antes de redistribuí-los.
