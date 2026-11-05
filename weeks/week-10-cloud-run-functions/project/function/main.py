"""Cloud Run function entry point: `rag_chat` is the --function target that
`gcloud run deploy --source . --function rag_chat` (see ../scripts/deploy_function.sh)
builds into a container image via buildpacks and deploys.

functions-framework, not FastAPI: a Cloud Run function is a single HTTP entry point,
and pulling in a full ASGI framework here would undercut the "lightweight" comparison
this week is built around (see ../../concept.md).
"""

from __future__ import annotations

import functions_framework
from flask import Request, jsonify

from app.pipeline import RAGPipeline
from app.tracing import traced_answer

from dotenv import load_dotenv

load_dotenv()

_pipeline = RAGPipeline()


@functions_framework.http
def rag_chat(request: Request):
    if request.method == "GET":
        return jsonify(status="ok")

    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "")
    if not question:
        return jsonify(error="question is required"), 400

    # Falls straight through to _pipeline.answer() unless LANGFUSE_* env vars are set; when
    # they are, flushes before returning (a function's instance is frozen after the response).
    result = traced_answer(_pipeline, question)
    return jsonify(
        answer=result.answer,
        retrieved_contexts=result.retrieved_contexts,
        retrieved_doc_ids=result.retrieved_doc_ids,
    )
