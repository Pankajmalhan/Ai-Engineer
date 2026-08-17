from contextlib import asynccontextmanager

from fastapi import FastAPI
from llama_index.core.schema import NodeWithScore, QueryBundle

from app import db
from app.retriever import DenseRetriever, HybridRRFRetriever, SparseRetriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.get_connection()
    app.state.conn = conn
    yield
    conn.close()


app = FastAPI(title="Hybrid Search (pgvector + pg_search + RRF)", lifespan=lifespan)


def _serialize(nodes: list[NodeWithScore]) -> list[dict]:
    return [
        {
            "id": int(n.node.id_),
            "title": n.node.metadata.get("title"),
            "content": n.node.text,
            "score": n.score,
        }
        for n in nodes
    ]


@app.get("/search/dense")
def search_dense(q: str, top_k: int = 10):
    retriever = DenseRetriever(app.state.conn, top_k=top_k)
    return _serialize(retriever.retrieve(QueryBundle(query_str=q)))


@app.get("/search/sparse")
def search_sparse(q: str, top_k: int = 10):
    retriever = SparseRetriever(app.state.conn, top_k=top_k)
    return _serialize(retriever.retrieve(QueryBundle(query_str=q)))


@app.get("/search/hybrid")
def search_hybrid(q: str, top_k: int = 10):
    retriever = HybridRRFRetriever(app.state.conn, top_k=top_k)
    return _serialize(retriever.retrieve(QueryBundle(query_str=q)))
