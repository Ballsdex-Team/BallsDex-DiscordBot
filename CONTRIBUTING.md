# Contributing

Thanks for contributing to this repo! This is a short guide to set you up for running Ballsdex in
a development environment, with some tips on the code structure.

## Setting up the environment

### PostgreSQL and Redis

Using Docker:

1. Install Docker.
2. Run `docker compose build` at the root of this repository.
3. Run `docker compose up -d postgres-db redis-cache`. This will not start the bot, only the
   database and redis server.

----

Without docker, check how to install and setup PostgreSQL and Redis-server on your OS.
Export the appropriate environment variables as described in the
[README](README.md#without-docker).

### Installing the dependencies

1. Get Python 3.13 and pip.
2. Install poetry with `pip install poetry`.
3. Run `poetry install`.
4. You may run commands inside the virtualenv with `poetry run ...`, or use `poetry shell`.

## Running the code

Before running any command, you must be in the poetry virtualenv, with the following
environment variables exported:

```bash
poetry shell
export BALLSDEXBOT_DB_URL="postgres://ballsdex:defaultballsdexpassword@localhost:5432/ballsdex"
export BALLSDEXBOT_REDIS_URL="redis://127.0.0.1"
```

If needed, feel free to change the host, port, user or password of the database or redis server.

### Starting the bot

```bash
python3 -m ballsdex --dev --debug
```

You can do `python3 -m ballsdex -h` to see the available options.

### Starting the admin panel

**Warning: You need to run migrations at least once before starting the admin
panel without the other components.** You can either run the bot once or do `aerich upgrade`.

```bash
uvicorn ballsdex.core.admin:_app --host 0.0.0.0 --reload
```

## Integrating your IDE

To have proper autocompletion and type checking, your IDE must be aware of your poetry virtualenv.

The path to Python can be obtained with `poetry env info -p`, copy that and configure your editor
to use it. Some editors like VS code may detect your poetry env automatically when picking
versions.

You can also install extensions to work with black, flake8 and pyright (Pylance for VS code).
Their configurations are already written in `pyproject.toml`, so it should work as-is.

## Migrations

When modifying the Tortoise models, you need to create a migration file to reflect the changes
everywhere. For this, we're using [aerich](https://github.com/tortoise/aerich).

### Applying the changes from remote

When new migrations are available, you can either start the bot to run them automatically, or
execute the following command:

```sh
aerich upgrade
```

### Creating new migrations

If you modified the models, `aerich` can automatically generate a migration file.

**You need to make sure you have already ran previous migrations, and that your database
is not messy!** Aerich's behaviour can be odd if not in ideal conditions.

Execute the following command to generate migrations, and push the created files:

```sh
aerich migrate
```

## Coding style

The code is formatted by `black`, style verified by `flake8`, and static checked by `pyright`.
They can be setup as a pre-commit hook to make them run before committing files:

```sh
pre-commit install
```

You can also run them manually:

```sh
pre-commit run -a
```
