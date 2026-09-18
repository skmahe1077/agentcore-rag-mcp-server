# Container image for the Cloud Operations Runbook Agent on AgentCore
# Runtime. Built and pushed by scripts/deploy.sh; terraform/agentcore.tf
# references the resulting image URI - Terraform itself never builds images.
#
# ARM64 by default (AgentCore Runtime microVMs support ARM64; cheaper than
# x86_64 for equivalent throughput). Build with:
#   docker build --platform linux/arm64 -f app/Dockerfile -t <repo>:<tag> .

FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies first for better layer caching.
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --create-home --uid 1000 agent

COPY app/agent /app/app/agent
COPY app/mcp_server /app/app/mcp_server
COPY app/__init__.py /app/app/__init__.py

RUN chown -R agent:agent /app
USER agent

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["python", "-m", "app.agent.main"]
