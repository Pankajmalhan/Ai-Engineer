# Resources

## From the roadmap (as given)

- **Primary**: CRAG paper — ["Corrective Retrieval Augmented Generation"](https://arxiv.org/abs/2401.15884) (Yan et al., 2024)
- **Secondary**: [DSPy: Getting Started](https://dspy.ai/) tutorial on dspy.ai — **deferred**, not yet used in this project (see concept.md's Overview); come back to this once DSPy itself has been learned on its own terms

## Added by Claude (thin spot: no router- or Instructor/Tavily/pgvector-specific resources were given)

- [Instructor docs](https://python.useinstructor.com/) — structured LLM output via Pydantic, used for the LLM-as-judge grader, rewriter, and refiner
- [Tavily API docs](https://docs.tavily.com/) — the web search fallback used when CRAG escalates
- [LangChain — Route logic based on input](https://python.langchain.com/docs/how_to/routing/) — the `RunnableBranch` / router-chain pattern referenced in concept.md's routing section
- [NirDiamant/RAG_Techniques — crag.ipynb](https://github.com/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/crag.ipynb) — a reference CRAG implementation (FAISS + dual threshold + query rewriting + knowledge refinement + generation) this project's `app/crag.py` was checked against and aligned to
- [pgvector](https://github.com/pgvector/pgvector) / [pgvector-python](https://github.com/pgvector/pgvector-python) — the Postgres vector extension and Python client backing `app/vectorstore.py`
