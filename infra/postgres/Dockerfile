# syntax=docker/dockerfile:1.7

ARG POSTGRES_BASE_IMAGE=postgres:18.4-trixie
FROM ${POSTGRES_BASE_IMAGE} AS pgvector-builder

ARG PG_MAJOR=18
ARG PGVECTOR_VERSION=0.8.2

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        git \
        postgresql-server-dev-${PG_MAJOR} \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "v${PGVECTOR_VERSION}" https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector OPTFLAGS="" \
    && make -C /tmp/pgvector install DESTDIR=/tmp/pgvector-install

FROM ${POSTGRES_BASE_IMAGE} AS timescaledb-builder

ARG PG_MAJOR=18
ARG TIMESCALEDB_VERSION=2.23.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        cmake \
        git \
        libssl-dev \
        postgresql-server-dev-${PG_MAJOR} \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${TIMESCALEDB_VERSION}" https://github.com/timescale/timescaledb.git /tmp/timescaledb \
    && cd /tmp/timescaledb \
    && ./bootstrap -DREGRESS_CHECKS=OFF \
    && cd build \
    && make -j"$(nproc)" \
    && make install DESTDIR=/tmp/timescaledb-install

FROM ${POSTGRES_BASE_IMAGE}

LABEL org.opencontainers.image.title="quimera-postgres-memory"
LABEL org.opencontainers.image.description="PostgreSQL 18.4 with TimescaleDB and pgvector for QUIMERA local memory"
LABEL org.opencontainers.image.source="https://github.com/franciscosalido/OPENCLAW"

ARG PG_MAJOR=18
ARG PGVECTOR_VERSION=0.8.2
ARG TIMESCALEDB_VERSION=2.23.0

ENV QUIMERA_POSTGRES_BASE_IMAGE=${POSTGRES_BASE_IMAGE}
ENV QUIMERA_PGVECTOR_VERSION=${PGVECTOR_VERSION}
ENV QUIMERA_TIMESCALEDB_VERSION=${TIMESCALEDB_VERSION}

COPY --from=pgvector-builder /tmp/pgvector-install/ /
COPY --from=timescaledb-builder /tmp/timescaledb-install/ /

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-${PG_MAJOR} \
    && rm -rf /var/lib/apt/lists/* \
    && test -f "/usr/share/postgresql/${PG_MAJOR}/extension/vector.control" \
    && test -f "/usr/share/postgresql/${PG_MAJOR}/extension/timescaledb.control"
