# syntax=docker/dockerfile:1.7-labs

FROM python:3.13.2-alpine3.21 AS base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    PATH="/opt/venv/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv

# Pillow runtime dependencies
# TODO: remove testing repository when alpine 3.22 is released (libraqm is only on edge for now)
RUN apk add --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/community libraqm-dev && \
    apk add --no-cache tiff-dev jpeg-dev openjpeg-dev zlib-dev freetype-dev \
    lcms2-dev libwebp-dev tcl-dev tk-dev harfbuzz-dev fribidi-dev \
    libimagequant-dev libxcb-dev libpng-dev libavif-dev

ARG UID GID
RUN addgroup -S ballsdex -g ${GID:-1000} && adduser -S ballsdex -G ballsdex -u ${UID:-1000}
WORKDIR /code

FROM base AS builder-base

# Pillow build dependencies
RUN apk add --no-cache gcc libc-dev

COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /uvx /bin/
COPY uv.lock pyproject.toml /code/
RUN --mount=type=cache,target=/root/.cache/ \
    uv venv $VIRTUAL_ENV && \
    uv sync --locked --no-install-project
COPY . /code/
RUN --mount=type=cache,target=/root/.cache/ \
    uv sync --locked

FROM base AS production
COPY --from=builder-base /opt/venv /opt/venv
USER ballsdex
