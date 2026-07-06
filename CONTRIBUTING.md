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

`docker-compose.override.yml` is loaded automatically if present, and is dedicated to local
development: it points the admin panel at `admin_panel.settings.dev`, and sets the
`INSTALL_DEV_DEPS` build argument so the `Dockerfile` installs the `dev` extra (`ruff`, `pyright`,
`pre-commit`, `django-debug-toolbar`, `pyinstrument`) inside the image. Production builds don't
set this argument, so deployed images stay lean.

This file is gitignored, so it won't be created for you — you need to add it yourself, with the
following contents:

```yaml
services:
  bot:
    command: python3 -m ballsdex --dev --debug
    environment:
      - "DJANGO_SETTINGS_MODULE=admin_panel.settings.dev"
    build:
      args:
        - "INSTALL_DEV_DEPS=1"
  admin-panel:
    environment:
      - "DJANGO_SETTINGS_MODULE=admin_panel.settings.dev"
    build:
      args:
        - "INSTALL_DEV_DEPS=1"
  migration:
    build:
      args:
        - "INSTALL_DEV_DEPS=1"
```

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

## Translations (i18n)

Two things are localized, both following the requesting user's Discord client locale, and both
backed by the same gettext catalogs - but through different mechanisms:

- Command names, descriptions, parameters and choices, via `discord.py`'s `Translator`/`locale_str`
  mechanism (`ballsdex.core.bot.Translator`).
- Runtime UI strings (embeds, messages, view/button labels), via `ballsdex.core.translation.t(...)`.
  Wrap any user-facing string with `t(...)`, and use `.format(...)` for dynamic values (channel
  mentions, counts, brand names, etc.) rather than f-strings, so the translated text isn't baked
  around a value from one specific invocation:

  ```python
  await interaction.response.send_message(
      t("Spawning is now enabled in {channel}.").format(channel=channel.mention)
  )
  ```

  `t` isn't called `_` on purpose: this codebase uses `_` pervasively as a throwaway variable
  (e.g. `player, _ = await Player.objects.aget_or_create(...)`), which would turn every such
  function into an `UnboundLocalError` trap if `_` were also a module-level import there.
  Avoid calling `t(...)` at import/class-definition time (e.g. as a module-level constant, or
  inside an `@app_commands.command`/`@button` decorator's `description`/`label` kwarg) - at that
  point there's no interaction yet, so it always resolves to English. Build such values inside a
  function instead, called per-interaction.

Both are unrelated to the language a player or server can pick for countryball display
(`ballsdex.core.i18n.resolve_locale`), which is only ever a language explicitly configured for
that purpose, never an arbitrary client locale. That third mechanism is backed by data, not
gettext catalogs: a `BallTranslation` row per (ball, language), editable as an inline on the
`Ball` admin page. `Ball.localized_name(language)` (and `localized_short_name`/
`localized_capacity_name`/`localized_capacity_description`) fall back to the base field when
`language` is `None` or no translation is configured. Translations are attached to the in-memory
`balls` cache at `load_cache()` time, so looking one up never costs an extra query.

Catalogs live under `ballsdex/locales/<discord-locale>/LC_MESSAGES/ballsdex.po` (the directory
name must match a [`discord.Locale`](https://discordpy.readthedocs.io/en/latest/api.html#discord.Locale)
value, e.g. `fr`, `de`, `es-ES`).

If you added/changed a command's name, description, parameter, or choice, or added/changed a
`t(...)` call, regenerate the template (requires a database connection, but not a bot token):

```sh
cd admin_panel
uv run python manage.py extract_command_strings
```

This extracts from two sources into the same `.pot`: the live command tree (walked directly,
since discord.py resolves descriptions from docstrings - parsing and shortening them - before
they ever reach the translator, so re-deriving those strings via static analysis would mean
duplicating that parsing logic), and a static scan of the `ballsdex` package for `t(...)` calls.

To add a new language, or pull in new/changed strings for an existing one:

```sh
# new language
uv run pybabel init -i ballsdex/locales/ballsdex.pot -d ballsdex/locales -D ballsdex -l <locale>

# update an existing one after the .pot changed
uv run pybabel update -i ballsdex/locales/ballsdex.pot -d ballsdex/locales -D ballsdex -l <locale>
```

Edit the resulting `.po` file's `msgstr` entries, then compile it and commit both the `.po` and
the compiled `.mo`:

```sh
uv run pybabel compile -d ballsdex/locales -D ballsdex
```

`pybabel` is part of the `dev` extra (`Babel`). The bot only needs `gettext` from the standard
library at runtime, so compiled `.mo` files must be committed for translations to take effect.

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
