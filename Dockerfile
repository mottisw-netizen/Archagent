# Archagent - the web application, packaged.
#
# This image is the Python side only: the agent, the web UI, the deterministic
# CAD drivers (JSON, headless DXF via ezdxf). It is NOT the Revit/AutoCAD
# add-in - that runs *inside* Revit/AutoCAD on Windows and is a separate,
# native install (see revit-addin/README.md, autocad-addin/README.md). This
# container talks to that add-in over the network, exactly as it would if you
# ran `archagent-web` directly on the host - see DOCKER.md for how a container
# reaches an add-in listening on the Windows machine it runs on.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Archagent" \
      org.opencontainers.image.description="AI municipal permit drawing review and correction agent"

# poppler-utils: pdftotext, for reading PDF municipal comments (ingest.py
# shells out to it exactly like it would outside a container - no code
# difference, just making sure the binary is on PATH).
#
# nodejs/npm: only to install the `claude` CLI below - the "claude-code"
# engine (web/engines.py: ClaudeCodeEngine) shells out to it. Debian's own
# packages are recent enough; this is not a build toolchain, just a runtime
# for one global npm package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils nodejs npm \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/* /root/.npm

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples

# claude-code here only adds the `claude-agent-sdk` Python package - the
# actual `claude` binary was installed above via npm. The CLI authenticates
# itself (Claude.ai subscription login, or an API key) the first time it
# runs; see DOCKER.md for how that survives a container restart.
RUN pip install --no-cache-dir -e ".[web,llm,dxf,claude-code]"

ENV ARCHAGENT_WORKSPACE=/data/projects
RUN mkdir -p /data/projects
VOLUME ["/data/projects"]

EXPOSE 8000

CMD ["archagent-web", "--host", "0.0.0.0", "--port", "8000"]
