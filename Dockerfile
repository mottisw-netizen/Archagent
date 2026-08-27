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
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples

# The claude-code engine additionally needs the `claude` CLI (Node-based) on
# PATH; it is deliberately not installed here to keep the image small and
# dependency-free by default. Without it the web app still runs fully on the
# "pipeline" engine (LLM via API key) - it just prints a one-line notice and
# disables the claude-code engine option. See DOCKER.md to add it.
RUN pip install --no-cache-dir -e ".[web,llm,dxf]"

ENV ARCHAGENT_WORKSPACE=/data/projects
RUN mkdir -p /data/projects
VOLUME ["/data/projects"]

EXPOSE 8000

CMD ["archagent-web", "--host", "0.0.0.0", "--port", "8000"]
