"""The same pipeline as a plain LangChain (LCEL) chain -- for the LangGraph-vs-LangChain
comparison. It composes retrieve -> prompt -> model as one left-to-right pipe. There is
no state object, no checkpointer, no thread_id: every call starts from nothing, so a
follow-up question has no idea what came before. To fake memory you'd have to carry the
history yourself and pass it in on every call.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from app.graph import SYSTEM_PROMPT, TOP_K
from app.retrieval import BM25Retriever


def build_chain(llm: BaseChatModel, retriever: BM25Retriever | None = None):
    retriever = retriever or BM25Retriever()
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT + "\n\nContext for this turn:\n{context}"), ("human", "{question}")]
    )
    return (
        {
            "context": RunnableLambda(
                lambda q: "\n\n".join(f"[{d.id}] {d.text}" for d in retriever.retrieve(q, k=TOP_K))
            ),
            "question": lambda q: q,
        }
        | prompt
        | llm
        | StrOutputParser()
    )
