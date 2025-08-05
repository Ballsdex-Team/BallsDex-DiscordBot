# syntax=docker/dockerfile:1.7-labs

FROM python:3.13.2-alpine3.21 AS base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    POETRY_NO_ANSI=1 \
    POETRY_INSTALLER_NO_BINARY="pillow"

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

COPY poetry.lock pyproject.toml /code/
RUN --mount=type=cache,target=/root/.cache/ \
    pip install poetry==2.0.1 && poetry install --no-root
COPY . /code/
RUN poetry install

FROM base AS production
COPY --from=builder-base --parents /usr/local/lib/python*/site-packages/ /
USER ballsdex
