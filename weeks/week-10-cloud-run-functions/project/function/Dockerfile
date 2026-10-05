# syntax=docker/dockerfile:1
#
# Only exists for the "Cloud Run service" arm of this week's benchmark (see
# ../scripts/deploy_service.sh) -- the "Cloud Run function" arm (deploy_function.sh)
# deploys this exact same app/ + main.py through `gcloud run deploy --source
# --function`, which builds its own image via Google Cloud buildpacks instead of this
# Dockerfile. Same code, two different packaging paths -- that's the variable this
# week's benchmark isolates.
#
# A first attempt at the service arm tried to reuse the *buildpacks-built* function
# image directly as a plain `gcloud run deploy --image` service. It failed: Cloud
# Run functions run under the CNB (Cloud Native Buildpacks) lifecycle launcher, which
# needs launch metadata Cloud Run's function-specific deploy path wires up invisibly;
# a bare `--image` deploy of the same digest hits "no such file or directory" because
# that wiring isn't there. See concept.md's "Common pitfalls" for the full story --
# this Dockerfile is the fix: a completely ordinary container, no CNB involved.
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY app/ ./app/

ENV PORT=8080
EXPOSE 8080

CMD exec functions-framework --target=rag_chat --port=$PORT
