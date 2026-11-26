# Jurisprudência (uso pessoal)

Banco de decisões judiciais com busca em português, organização pessoal (pastas, tags,
favoritos, anotações, relações entre precedentes) e controle de origem/alterações.
Dimensionado para **milhões de decisões** em um único PostgreSQL.

## Subir

Requisitos: Docker.

```bash
docker compose up -d --build        # banco + API + página
# abra http://localhost:8000
```

Na primeira subida o banco cria as tabelas (`db/01_schema.sql`) e cadastra os
tribunais (`db/02_tribunais.sql`).

## Importar decisões

Há 5 decisões **fictícias** em `dados/exemplo.jsonl` só para testar o fluxo:

```bash
docker compose exec api python -m importador.importar \
    --arquivo /app/dados/exemplo.jsonl --tribunal STJ --fonte "Exemplo (fictício)"
```

Apague-as depois: `DELETE FROM decisoes WHERE fonte = 'Exemplo (fictício)';`

Para dados reais, converta o que o tribunal fornece para JSONL (uma decisão por linha)
ou CSV. Se as colunas tiverem outros nomes, use `--mapa`:

```json
{ "fonte_id": "id_documento", "ementa": "ementa", "numero_processo": "processo",
  "relator": "ministro_relator", "data_julgamento": "dt_julgamento",
  "inteiro_teor": "texto_integral", "orgao_julgador": "orgao" }
```

```bash
docker compose exec api python -m importador.importar \
    --arquivo /app/dados/stj_2024.jsonl --tribunal STJ --fonte "STJ dados abertos" \
    --mapa /app/dados/mapa_stj.json
```

O importador carrega em lotes de 5.000 com `COPY`, não duplica (chave: tribunal + `fonte_id`),
só atualiza quando o conteúdo mudou (hash) e guarda a mudança de ementa/tese/vigência em
`historico_alteracoes`. Cada execução fica registrada em `coletas`.

### Onde conseguir os dados

Use fontes oficiais e respeite os termos de uso de cada uma:

- Portais de dados abertos do **STJ** e do **STF**
- **DataJud** (CNJ): metadados de processos, não traz o inteiro teor
- Portais de jurisprudência de cada tribunal (verifique se permitem coleta automatizada)

Decisões podem conter dados pessoais: mantenha o banco apenas na sua máquina/rede e
trate-o conforme a LGPD.

## Busca

A caixa aceita sintaxe de buscador: `"frase exata"`, `termo1 OR termo2`, `-excluir`.
A ementa pesa mais que a tese, que pesa mais que o inteiro teor. Acentos são ignorados.
A contagem para em 10.000 ("mais de 10.000 resultados") para manter a resposta rápida.

## Estrutura

```
db/            schema SQL + cadastro de tribunais
backend/app    API FastAPI (busca, leitura, pastas, tags, notas, relações)
backend/importador   importação em massa JSONL/CSV
frontend/      página de consulta (HTML/JS puro)
dados/         arquivos para importar
```

API interativa em http://localhost:8000/docs.

## Próximos passos

1. **Coletores por tribunal**: um adaptador por fonte que baixa e gera o JSONL.
2. **Busca semântica**: a tabela `decisao_embeddings` (pgvector) já existe; falta gerar os
   embeddings e criar o índice HNSW.
3. **Alertas** de mudança de entendimento usando `buscas_salvas` + `historico_alteracoes`.
4. **Resumo por IA** com revisão humana (risco de erro/alucinação em texto jurídico).
5. Se passar de ~20–50 milhões de decisões ou a busca ficar lenta: mover a busca para
   OpenSearch/Meilisearch mantendo o PostgreSQL como fonte da verdade.

## Aviso

Ferramenta de pesquisa e organização. Confira sempre a decisão na fonte oficial antes de
citar. O campo `status` (vigente/superada) é manual ou depende da sua curadoria.
