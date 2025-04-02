# syntax=docker/dockerfile:1

FROM python:3.13.2-alpine3.21

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  PYTHONDONTWRITEBYTECODE=1

RUN pip install poetry==2.0.1

WORKDIR /code

COPY poetry.lock pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-root && rm -rf $POETRY_CACHE_DIR

COPY . /code

RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi
