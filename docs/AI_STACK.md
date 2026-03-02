# Structorium AI Stack (Neo4j + Turbopuffer + OpenAI + Cohere)

This project supports optional AI context enrichment for holistic review packets.

## Providers

- Graph database: `Neo4j` (local Docker recommended)
- Vector database: `Turbopuffer`
- Embeddings: `OpenAI /v1/embeddings`
- Reranking: `Cohere /v2/rerank`

## 1) Start Neo4j locally (Docker)

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Default local credentials from `docker-compose.neo4j.yml`:

- URI: `bolt://localhost:7687`
- User: `neo4j`
- Password: `structorium-dev-password`
- Browser: `http://localhost:7474`

## 2) Install AI extras

```bash
pip install -e ".[ai]"
```

## 3) Export credentials

```bash
export OPENAI_API_KEY="..."
export COHERE_API_KEY="..."
export TURBOPUFFER_API_KEY="..."

export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="structorium-dev-password"
export NEO4J_DATABASE="neo4j"
```

Optional Turbopuffer settings:

```bash
export TURBOPUFFER_NAMESPACE="structorium-code"
export TURBOPUFFER_REGION="aws-us-west-2"
```

## 4) Enable AI in Structorium config

```bash
structorium config set ai_enabled true
structorium config set ai_include_in_review true
```

Optional tuning:

```bash
structorium config set ai_embedding_model text-embedding-3-large
structorium config set ai_retrieval_top_k 24
structorium config set ai_rerank_top_n 10
structorium config set ai_chunk_chars 1800
structorium config set ai_chunk_overlap_chars 240
structorium config set ai_turbopuffer_namespace structorium-code
structorium config set ai_neo4j_uri bolt://localhost:7687
structorium config set ai_neo4j_user neo4j
structorium config set ai_neo4j_database neo4j
```

## 5) Run review prepare

```bash
structorium review --prepare
```

When AI is enabled and credentials are available, the generated packet now includes:

- top semantic retrieval hits (`ai_context.vector.top_hits`)
- graph neighbor data from Neo4j (`ai_context.graph.neighbors`)
- provider readiness/status diagnostics (`ai_context.provider_status`)

