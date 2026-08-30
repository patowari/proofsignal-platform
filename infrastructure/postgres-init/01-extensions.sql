-- Extensions required before migrations run.
--
-- vector: pgvector, for semantic retrieval over claim and document embeddings.
-- pg_trgm: trigram matching, used for fuzzy title/entity comparison during
--          near-duplicate detection.
-- unaccent: strips diacritics so full-text search matches across accent
--           variations.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
