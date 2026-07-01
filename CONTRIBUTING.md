# Contributing

Thanks for contributing to this repo! This is a short guide to set you up for running Ballsdex in
a development environment, with some tips on the code structure.

## Setting up the environment

### PostgreSQL

Using Docker:
1. Install Docker.
2. Run `docker compose up -d postgres-db`. This will start the database. It doesn't need the
   rest of the images to be built first.

Without docker, check how to install and setup PostgreSQL on your OS.
Export the appropriate environment variables as described in the
[no-docker installation guide](docs/selfhosting/installation/installing-ballsdex-no-docker.md).

### Installing the dependencies

1. Get Python 3.14.
2. Install uv with `pip install uv` (or see [uv installation](https://docs.astral.sh/uv/getting-started/installation/)).
3. Run `uv sync --extra dev`. The `dev` extra pulls in `ruff`, `pyright`, `pre-commit` and the
   admin panel's debug tools (`django-debug-toolbar`, `pyinstrument`), all used later in this guide.
4. You may run commands inside the virtualenv with `uv run ...`.


## Running the code

Before running any command, make sure the following environment variables are configured in your shell:

```bash
export BALLSDEXBOT_DB_URL="postgres://ballsdex:defaultballsdexpassword@localhost:5432/ballsdex"
```

If needed, feel free to change the host, port, or user/password of the database.

### Starting the bot

```bash
uv run python -m ballsdex --dev --debug
```

You can do `python3 -m ballsdex -h` to see the available options.

### Starting the admin panel

```bash
cd admin_panel
export DJANGO_SETTINGS_MODULE=admin_panel.settings.dev
uv run python manage.py migrate
uv run python manage.py collectstatic --no-input
uv run uvicorn --reload --reload-include "*.html" admin_panel.asgi:application
```

You will be running the admin panel with additional debug tools. There is the django debug
toolbar to inspect SQL queries, loading times, template loading and other tools. You also get
pyinstrument, allowing you to profile a page by appending `?profile` at the end.

> [!TIP]
> `uv run python manage.py` contains a lot of commands, feel free to explore them! To name a few:
>
> - `shell` launches a Python REPL ready to interact with models and database
> - `dbshell` will launch `psql` with the right settings for the database
> - `check` performs general system checks to ensure everything works
> - `createsuperuser` creates a superuser account
> - `showmigrations` shows the applied/missing migrations

> [!WARNING]
> Do not use `python3 manage.py runserver` to run the server, since the bot relies on async code.
> Django must be started with an ASGI server, not the default WSGI.

### Running everything with Docker

As an alternative to the native setup above, you can run the whole stack (bot, admin panel,
migrations, proxy) through Docker Compose instead:

```bash
docker compose build
docker compose up -d
```

`docker-compose.override.yml` is loaded automatically and is dedicated to local development: it
points the admin panel at `admin_panel.settings.dev`, and sets the `INSTALL_DEV_DEPS` build
argument so the `Dockerfile` installs the `dev` extra (`ruff`, `pyright`, `pre-commit`,
`django-debug-toolbar`, `pyinstrument`) inside the image. Production builds don't set this
argument, so deployed images stay lean.

You can then run tooling inside the containers, for example:

```bash
docker compose exec bot ruff check .
docker compose exec bot pyright .
```

## Integrating your IDE

To have proper autocompletion and type checking, your IDE must be aware of your uv virtualenv.

You can configure your editor to use the uv virtual environment. Some editors like VS code may
detect it automatically when picking versions.

You can also install extensions to work with ruff and pyright (Pylance for VS code).
Their configurations are already written in `pyproject.toml`, so it should work as-is.

## Migrations

If you are modifying model definitions in `admin_panel/bd_models/models.py`, you need migrations
to update the database schema.

From the `admin_panel` directory, run `uv run python manage.py makemigrations bd_models` to
generate a migration file. Re-read its contents to ensure there is only what you modified, and
commit it.

You can read more about migrations
[here](https://docs.djangoproject.com/en/6.0/topics/migrations/), the engine is very extensive!

## Coding style

The code is formatted and linted by `ruff`, and static checked by `pyright`.
They can be setup as a pre-commit hook to make them run before committing files:

```sh
pre-commit install
```

You can also run them manually:

```sh
pre-commit run -a
```

All rules are defined in `pyproject.toml`, meaning your editor will pick them up if you install
the right tools.
