CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

DROP TABLE IF EXISTS documents;

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL
);

-- Dense candidate list: approximate nearest-neighbor index over the embedding column.
CREATE INDEX documents_embedding_hnsw_idx
    ON documents USING hnsw (embedding vector_cosine_ops);

-- Sparse candidate list: BM25 index (pg_search / ParadeDB) over the text column.
-- key_field must be the table's unique key; it's how @@@ results map back to rows.
CREATE INDEX documents_bm25_idx
    ON documents USING bm25 (id, content)
    WITH (key_field = 'id');
