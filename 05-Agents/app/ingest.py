"""Load the runbooks in knowledge-base/, split them into chunks, embed them and store them in Postgres.

Run from the 03-RAG folder:  python -m app.ingest
Re-running is safe: the table is emptied and filled again.
"""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from fastembed import TextEmbedding
from pgvector.psycopg import register_vector

# Reads DATABASE_URL from the .env in the repo root
load_dotenv()

KB_DIR = Path(__file__).resolve().parents[2] / "knowledge-base"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://devops:devops@127.0.0.1:5435/knowledge")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim vectors
MAX_WORDS = 150  # the model only reads the first ~256 tokens of a chunk

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
    id        bigserial PRIMARY KEY,
    source    text NOT NULL,
    text      text NOT NULL,
    embedding vector(384) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
"""


def split_blocks(body: str) -> list[str]:
    """Split on blank lines, but never inside a ``` code fence."""
    blocks, current, in_code = [], [], False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        if not line.strip() and not in_code:
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def chunk_markdown(md: str) -> list[str]:
    """One chunk per '## ' section, prefixed with the doc title so each chunk has context.
    Long sections are packed into several chunks of up to MAX_WORDS words."""
    lines = md.strip().splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("# ") else ""
    sections, current = [], []
    for line in lines[1:] if title else lines:
        if line.startswith("## ") and current:
            sections.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        sections.append("\n".join(current))

    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        heading, _, body = section.partition("\n")
        if not heading.startswith("## "):  # intro text before the first section
            heading, body = "", section
        prefix = f"# {title}\n{heading}".strip()

        packed, words = [], 0
        for block in split_blocks(body):
            n = len(block.split())
            if packed and words + n > MAX_WORDS:
                chunks.append(prefix + "\n" + "\n\n".join(packed))
                packed, words = [], 0
            packed.append(block)
            words += n
        if packed:
            chunks.append(prefix + "\n" + "\n\n".join(packed))
    return chunks


def main():
    files = sorted(KB_DIR.glob("*.md"))
    rows = [(f.name, text) for f in files for text in chunk_markdown(f.read_text(encoding="utf-8"))]
    print(f"{len(files)} files -> {len(rows)} chunks")

    model = TextEmbedding(EMBED_MODEL)
    embeddings = list(model.embed([text for _, text in rows]))

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(SCHEMA)
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE chunks RESTART IDENTITY")
            cur.executemany(
                "INSERT INTO chunks (source, text, embedding) VALUES (%s, %s, %s)",
                [(source, text, emb) for (source, text), emb in zip(rows, embeddings)],
            )
    print(f"Stored {len(rows)} chunks in the chunks table")


if __name__ == "__main__":
    main()
