# Contributing

Thanks for contributing to this repo! This is a short guide to set you up for running Ballsdex in
a development environment, with some tips on the code structure.

## Setting up the environment

### PostgreSQL

Using Docker:

1. Install Docker.
2. Copy `.env.example` to `.env` and change the database password.
3. Run `docker compose build` at the root of this repository.
4. Run `docker compose up -d postgres-db`. This will not start the bot, only the database.

----

Without docker, check how to install and setup PostgreSQL on your OS.
Export the appropriate environment variables as described in the
[README](README.md#without-docker).

### Installing the dependencies

1. Install [uv](https://docs.astral.sh/uv/) and Python 3.14.
2. Run `uv sync --all-extras` at the root of this repository.
3. Run commands with `uv run ...`, or activate the virtualenv in `.venv/`.

## Running the code

Before running any command, export the following environment variables:

```bash
export BALLSDEXBOT_DB_URL="postgres://ballsdex:defaultballsdexpassword@localhost:5432/ballsdex"
```

If needed, feel free to change the host, port, user or password of the database.

### Starting the bot

```bash
uv run python3 -m ballsdex --dev --debug
```

You can do `uv run python3 -m ballsdex -h` to see the available options.

### Starting the admin panel

```bash
cd admin_panel
export DJANGO_SETTINGS_MODULE=admin_panel.settings.dev
uv run python3 manage.py migrate
uv run python3 manage.py collectstatic --no-input
uv run uvicorn --reload --reload-include "*.html" admin_panel.asgi:application
```

You will be running the admin panel with additional debug tools. There is the django debug
toolbar to inspect SQL queries, loading times, template loading and other tools. You also get
pyinstrument, allowing you to profile a page by appending `?profile` at the end.

> [!TIP]
> `python3 manage.py` contains a lot of commands, feel free to explore them! To name a few:
>
> - `shell` launches a Python REPL ready to interact with models and database
> - `dbshell` will launch `psql` with the right settings for the database
> - `check` performs general system checks to ensure everything works
> - `createsuperuser` creates a superuser account
> - `showmigrations` shows the applied/missing migrations

> [!WARNING]
> Do not use `python3 manage.py runserver` to run the server, since the bot relies on async code.
> Django must be started with an ASGI server, not the default WSGI.

## Integrating your IDE

To have proper autocompletion and type checking, your IDE must be aware of the project virtualenv
created by uv in `.venv/`.

Configure your editor to use `.venv/bin/python`. VS Code should detect the environment
automatically when opening the repository (see `.vscode/settings.json`).

You can also install extensions to work with ruff and pyright (Pylance for VS code).
Their configurations are already written in `pyproject.toml`, so it should work as-is.

## Migrations

If you are modifying model definitions, you need migrations to update the database schema.

Edit models in `admin_panel/bd_models/models.py`, then run
`uv run python3 manage.py makemigrations` from the `admin_panel/` directory to generate a migration
file. Re-read its contents to ensure there is only what you modified, and commit it.

You can read more about migrations
[here](https://docs.djangoproject.com/en/6.0/topics/migrations/), the engine is very extensive!

## Coding style

The code is formatted and linted by `ruff`, and statically checked by `pyright`.
They can be setup as a pre-commit hook to make them run before committing files:

```sh
uv run pre-commit install
```

You can also run them manually:

```sh
uv run pre-commit run -a
```

All rules are defined in `pyproject.toml`, meaning your editor will pick them up if you install
the right tools.
