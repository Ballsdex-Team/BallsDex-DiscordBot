# syntax=docker/dockerfile:1.7-labs

FROM python:3.14.0-alpine3.22 AS base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    PATH="/opt/venv/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    BALLSDEX_LOG_DIR=/var/log/ballsdex \
    BALLSDEXBOT_EXTRA_TOML=/code/admin_panel/config/extra.toml \
    STATIC_ROOT=/var/www/ballsdex/static \
    DJANGO_SETTINGS_MODULE=admin_panel.settings

# Pillow runtime dependencies
# TODO: remove testing repository when alpine 3.22 is released (libraqm is only on edge for now)
RUN apk add --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/community libraqm-dev && \
    apk add --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/main postgresql18-client && \
    apk add --no-cache tiff-dev jpeg-dev openjpeg-dev zlib-dev freetype-dev \
    lcms2-dev libwebp-dev tcl-dev tk-dev harfbuzz-dev fribidi-dev \
    libimagequant-dev libxcb-dev libpng-dev libavif-dev

ARG UID GID
RUN addgroup -S ballsdex -g ${GID:-1000} && \
    adduser -S ballsdex -G ballsdex -u ${UID:-1000} && \
    mkdir -p -m 770 ${BALLSDEX_LOG_DIR} && chown ballsdex:ballsdex ${BALLSDEX_LOG_DIR}
WORKDIR /code

FROM base AS builder-base

# Pillow build dependencies
RUN apk add --no-cache gcc libc-dev git

COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /uvx /bin/
COPY uv.lock pyproject.toml /code/
RUN --mount=type=cache,target=/root/.cache/ \
    uv venv $VIRTUAL_ENV && \
    uv sync --locked --no-install-project --no-editable --active
COPY --parents admin_panel ballsdex LICENSE README.md /code/
RUN --mount=type=cache,target=/root/.cache/ \
    uv sync --locked --no-editable --active --reinstall-package ballsdex && \
    cd admin_panel && django-admin collectstatic --no-input

# this is running in a separate layer to allow bots with different extra packages to run on the same base layer
COPY --parents bdextra.py config/extra.toml extra /code/
RUN --mount=type=cache,target=/root/.cache/ \
    if [ -f config/extra.toml ]; then uv pip install --reinstall $(python3 bdextra.py config/extra.toml); fi

FROM nginx:1.29.3-alpine3.22 AS proxy
COPY --from=builder-base /var/www/ballsdex/static /var/www/ballsdex/static

FROM base AS production
COPY --from=builder-base /opt/venv /opt/venv
WORKDIR /code/admin_panel
USER ballsdex
