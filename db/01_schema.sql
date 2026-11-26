-- =====================================================================
-- Banco de jurisprudência (uso pessoal, escala de milhões de decisões)
-- PostgreSQL 16 + pgvector
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

-- Busca full-text em português ignorando acentos
CREATE TEXT SEARCH CONFIGURATION pt_unaccent (COPY = portuguese);
ALTER TEXT SEARCH CONFIGURATION pt_unaccent
    ALTER MAPPING FOR hword, hword_part, word
    WITH unaccent, portuguese_stem;

-- ---------------------------------------------------------------------
-- Cadastros
-- ---------------------------------------------------------------------
CREATE TABLE tribunais (
    id          smallserial PRIMARY KEY,
    sigla       text NOT NULL UNIQUE,          -- STF, STJ, TJCE, TRF5...
    nome        text NOT NULL,
    ramo        text NOT NULL,                 -- superior, federal, estadual, trabalho, eleitoral, militar
    uf          char(2)
);

CREATE TABLE orgaos_julgadores (
    id          serial PRIMARY KEY,
    tribunal_id smallint NOT NULL REFERENCES tribunais(id),
    nome        text NOT NULL,                 -- "Segunda Turma", "3ª Câmara Cível"...
    UNIQUE (tribunal_id, nome)
);

-- ---------------------------------------------------------------------
-- Decisões
-- ---------------------------------------------------------------------
CREATE TYPE tipo_decisao AS ENUM (
    'acordao', 'decisao_monocratica', 'sumula', 'sumula_vinculante',
    'repercussao_geral', 'recurso_repetitivo', 'iac', 'irdr', 'outro'
);

CREATE TYPE status_vigencia AS ENUM ('vigente', 'superada', 'revogada', 'desconhecido');

CREATE TABLE decisoes (
    id                bigserial PRIMARY KEY,
    tribunal_id       smallint NOT NULL REFERENCES tribunais(id),
    orgao_julgador_id integer REFERENCES orgaos_julgadores(id),
    tipo              tipo_decisao NOT NULL DEFAULT 'acordao',
    numero_processo   text,                    -- como veio da fonte
    numero_cnj        text,                    -- NNNNNNN-DD.AAAA.J.TR.OOOO
    classe            text,                    -- REsp, HC, AgInt, RE...
    relator           text,
    data_julgamento   date,
    data_publicacao   date,
    ementa            text,
    inteiro_teor      text,
    tese              text,                    -- tese fixada, quando houver
    legislacao_citada jsonb NOT NULL DEFAULT '[]'::jsonb,
    precedentes_citados jsonb NOT NULL DEFAULT '[]'::jsonb,
    status            status_vigencia NOT NULL DEFAULT 'desconhecido',

    -- Rastreabilidade (confiabilidade jurídica)
    fonte             text NOT NULL,           -- "STJ dados abertos", "TJCE portal"...
    fonte_id          text NOT NULL,           -- id da decisão na fonte
    fonte_url         text,
    hash_conteudo     text NOT NULL,           -- detecta mudança na recoleta
    coletado_em       timestamptz NOT NULL DEFAULT now(),
    atualizado_em     timestamptz NOT NULL DEFAULT now(),

    -- Índice de busca: ementa pesa mais que tese, que pesa mais que o inteiro teor
    busca tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('pt_unaccent'::regconfig, coalesce(ementa, '')), 'A') ||
        setweight(to_tsvector('pt_unaccent'::regconfig, coalesce(tese, '')),   'B') ||
        setweight(to_tsvector('pt_unaccent'::regconfig, left(coalesce(inteiro_teor, ''), 400000)), 'C')
    ) STORED,

    UNIQUE (tribunal_id, fonte_id)
);

CREATE INDEX idx_decisoes_busca        ON decisoes USING gin (busca);
CREATE INDEX idx_decisoes_tribunal_dt  ON decisoes (tribunal_id, data_julgamento DESC);
CREATE INDEX idx_decisoes_data         ON decisoes (data_julgamento DESC);
CREATE INDEX idx_decisoes_cnj          ON decisoes (numero_cnj);
CREATE INDEX idx_decisoes_processo     ON decisoes (numero_processo);
CREATE INDEX idx_decisoes_relator_trgm ON decisoes USING gin (relator gin_trgm_ops);
CREATE INDEX idx_decisoes_leg          ON decisoes USING gin (legislacao_citada);

-- ---------------------------------------------------------------------
-- Busca semântica (opcional): preencha depois com embeddings
-- Ajuste a dimensão ao modelo escolhido (768, 1024, 1536...)
-- ---------------------------------------------------------------------
CREATE TABLE decisao_embeddings (
    decisao_id  bigint PRIMARY KEY REFERENCES decisoes(id) ON DELETE CASCADE,
    modelo      text NOT NULL,
    embedding   vector(1024) NOT NULL
);
-- Crie o índice depois de popular a tabela:
-- CREATE INDEX idx_emb_hnsw ON decisao_embeddings USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------
-- Organização pessoal
-- ---------------------------------------------------------------------
CREATE TABLE pastas (
    id        serial PRIMARY KEY,
    nome      text NOT NULL,
    pai_id    integer REFERENCES pastas(id) ON DELETE CASCADE,
    criada_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (pai_id, nome)
);

CREATE TABLE decisao_pasta (
    decisao_id bigint  NOT NULL REFERENCES decisoes(id) ON DELETE CASCADE,
    pasta_id   integer NOT NULL REFERENCES pastas(id)   ON DELETE CASCADE,
    PRIMARY KEY (decisao_id, pasta_id)
);

CREATE TABLE tags (
    id   serial PRIMARY KEY,
    nome text NOT NULL UNIQUE
);

CREATE TABLE decisao_tag (
    decisao_id bigint  NOT NULL REFERENCES decisoes(id) ON DELETE CASCADE,
    tag_id     integer NOT NULL REFERENCES tags(id)     ON DELETE CASCADE,
    PRIMARY KEY (decisao_id, tag_id)
);

CREATE TABLE favoritos (
    decisao_id bigint PRIMARY KEY REFERENCES decisoes(id) ON DELETE CASCADE,
    criado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE anotacoes (
    id         bigserial PRIMARY KEY,
    decisao_id bigint NOT NULL REFERENCES decisoes(id) ON DELETE CASCADE,
    texto      text NOT NULL,
    trecho     text,                            -- trecho destacado da decisão
    criada_em  timestamptz NOT NULL DEFAULT now(),
    atualizada_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_anotacoes_decisao ON anotacoes (decisao_id);

-- Relações entre decisões: precedente, distinção, superação...
CREATE TYPE tipo_relacao AS ENUM (
    'segue', 'cita', 'distingue', 'supera', 'superada_por', 'confirma', 'contraria'
);

CREATE TABLE relacoes_decisoes (
    id         bigserial PRIMARY KEY,
    origem_id  bigint NOT NULL REFERENCES decisoes(id) ON DELETE CASCADE,
    destino_id bigint NOT NULL REFERENCES decisoes(id) ON DELETE CASCADE,
    tipo       tipo_relacao NOT NULL,
    nota       text,
    criada_em  timestamptz NOT NULL DEFAULT now(),
    CHECK (origem_id <> destino_id),
    UNIQUE (origem_id, destino_id, tipo)
);
CREATE INDEX idx_relacoes_destino ON relacoes_decisoes (destino_id);

-- Buscas salvas (base para alertas futuros)
CREATE TABLE buscas_salvas (
    id        serial PRIMARY KEY,
    nome      text NOT NULL,
    consulta  text NOT NULL,
    filtros   jsonb NOT NULL DEFAULT '{}'::jsonb,
    criada_em timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Controle: histórico de alterações e log de coletas
-- ---------------------------------------------------------------------
CREATE TABLE historico_alteracoes (
    id         bigserial PRIMARY KEY,
    decisao_id bigint NOT NULL REFERENCES decisoes(id) ON DELETE CASCADE,
    campo      text NOT NULL,
    valor_antigo text,
    valor_novo   text,
    alterado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE coletas (
    id          bigserial PRIMARY KEY,
    fonte       text NOT NULL,
    iniciada_em timestamptz NOT NULL DEFAULT now(),
    finalizada_em timestamptz,
    inseridas   integer NOT NULL DEFAULT 0,
    atualizadas integer NOT NULL DEFAULT 0,
    ignoradas   integer NOT NULL DEFAULT 0,
    erros       integer NOT NULL DEFAULT 0,
    observacao  text
);

-- Atualiza atualizado_em e registra mudança de status/ementa/tese
CREATE OR REPLACE FUNCTION trg_decisoes_historico() RETURNS trigger AS $$
BEGIN
    NEW.atualizado_em := now();
    IF NEW.ementa IS DISTINCT FROM OLD.ementa THEN
        INSERT INTO historico_alteracoes (decisao_id, campo, valor_antigo, valor_novo)
        VALUES (OLD.id, 'ementa', OLD.ementa, NEW.ementa);
    END IF;
    IF NEW.tese IS DISTINCT FROM OLD.tese THEN
        INSERT INTO historico_alteracoes (decisao_id, campo, valor_antigo, valor_novo)
        VALUES (OLD.id, 'tese', OLD.tese, NEW.tese);
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO historico_alteracoes (decisao_id, campo, valor_antigo, valor_novo)
        VALUES (OLD.id, 'status', OLD.status::text, NEW.status::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER decisoes_historico
    BEFORE UPDATE ON decisoes
    FOR EACH ROW EXECUTE FUNCTION trg_decisoes_historico();
