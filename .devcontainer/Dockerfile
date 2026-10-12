# Development and verification environment.
# `tools` holds exactly what scripts/verify.py needs (docs/VERIFY.md); `dev` adds Claude Code.
# Keep Python, Node and PostgreSQL majors in step with .github/workflows/lint.yml.
FROM node:22-bookworm-slim AS node

FROM python:3.13-bookworm AS tools

COPY --from=node /usr/local/bin/node /usr/local/bin/
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# PostgreSQL 16 tools for `verify.py --with-db`, which creates its own private cluster.
# No cluster is created or started here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-common \
    && sed -i 's/^#*\s*create_main_cluster.*/create_main_cluster = false/' \
        /etc/postgresql-common/createcluster.conf \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get install -y --no-install-recommends postgresql-16 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/usr/lib/postgresql/16/bin:$PATH

# initdb refuses to run as root, so verification runs as an ordinary user.
RUN useradd --create-home --shell /bin/bash --uid 1000 dev
USER dev

FROM tools AS dev

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends sudo \
    && rm -rf /var/lib/apt/lists/* \
    && echo "dev ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/dev \
    && chmod 0440 /etc/sudoers.d/dev
USER dev

# Download to a file first so a failed download fails the layer instead of piping nothing to bash.
RUN curl -fsSL -o /tmp/claude-install.sh https://claude.ai/install.sh \
    && bash /tmp/claude-install.sh \
    && rm /tmp/claude-install.sh \
    && /home/dev/.local/bin/claude --version \
    && mkdir -p /home/dev/.claude
ENV PATH=/home/dev/.local/bin:$PATH
