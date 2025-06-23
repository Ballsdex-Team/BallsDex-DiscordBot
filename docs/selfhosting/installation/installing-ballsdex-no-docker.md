The recommended way to run Ballsdex is using Docker, but you may have reasons to run it without this dependency.

This install method is supported but only recommended for the advanced users, there are a lot of additional steps and dependencies to manage yourself.

!!! info
    Few commands will be given, but online guides are given instead. This is because instructions differ between operating systems, so you have to use what's best for you.

## 1. Setting up the database

Install [PostgreSQL](https://www.postgresql.org/download/) and start it. Create a database by following [this guide](https://www.postgresql.org/docs/current/tutorial-createdb.html).

You must then have a link to connect to the database in the following format: `postgres://username:password@localhost:5432/database_name`

Test that your database is up with the following command: `psql -c "\l" postgres://username:password@localhost:5432/database_name`  
Check that your database appears in the list and that your user is the owner.

## 2. Requirements

### Python 3.13

You must have the latest version of Python installed on your system. Given that it's new, it's unlikely that your system ships with the right Python version (check with `python3.13 -V`).

On Linux/macOS, [pyenv](https://github.com/pyenv/pyenv) is a good tool for compiling any python version. You can also search instructions for your system to download pre-built binaries.

Check that you also have access to pip with `python3.13 -m pip -V`

### Poetry

You also need poetry, our package manager, to install the dependencies.

Run `python3.13 -m pip install -U poetry` to install it.

### git

[Git](https://git-scm.com/downloads) is needed to download and update the source code.

### Create a Discord bot account

You must first setup a Discord bot account. You can follow [discord.py's tutorial](https://discordpy.readthedocs.io/en/latest/discord.html) to create and invite your bot.

For now, don't copy your token, but keep the page open.

Once this is configured, you also **need to enable message content intent**. Go to the "Bot" tab of your application, scroll down to "Privileged intents" and tick "Message content".

!!! info
    You can fill the description of your application, it will appear under the "About me" section.

## 3. Download the source code

Type the following command to download the latest version of the bot:

```
git clone https://github.com/laggron42/BallsDex-DiscordBot.git
```

Then you can use the command cd to change directory and open the folder you just downloaded:

```
cd BallsDex-DiscordBot
```

## 4. Installing the bot

1. `poetry install` to download and install the bot's dependencies.
2. `poetry shell` to open the virtual environment where your dependencies are
3. `python3 -m ballsdex --version` to check that the bot loads successfully
4. `python3 -m ballsdex --reset-settings` to create the default configuration file
5. `cd admin_panel`
6. `python3 manage.py migrate` to initialize the database
7. `python3 manage.py collectstatic --no-input` to initialize the admin panel
8. `cd ..` (return to the previous directory for the next steps)

## 5. Configure the bot

Follow [this section](../installing-ballsdex/#5-configure-the-bot) from the main tutorial to fill the base settings.

## 6. Run the bot

Before running the bot, you must tell it about your database. Export the `BALLSDEXBOT_DB_URL` environment variable with the link to Postgres you tested earlier:

- Linux/macOS: `export BALLSDEXBOT_DB_URL=postgres://username:password@localhost:5432/database_name`
- Windows: `$Env.BALLSDEXBOT_DB_URL = 'postgres://username:password@localhost:5432/database_name'`

Then, run `python3 -m ballsdex` to start the bot! To shut it down, type Ctrl+C.

!!! tip
    There are multiple options available when running the bot, do `python3 -m ballsdex -h` to view them.

### Running the admin panel

1. Open another shell with `poetry shell` enabled and the environment variables exported
2. `cd admin_panel && uvicorn admin_panel.asgi:application`
3. Follow [this guide](../admin-panel/getting-started.md) afterwards

---

## Summary

Before running any command, do these:

1. `cd BallsDex-DiscordBot` (open the bot's directory)
2. `poetry shell` (activate the virtual environment)
3. `export BALLSDEXBOT_DB_URL=postgres://username:password@localhost:5432/database_name`

Then

- Start the bot: `python3 -m ballsdex`
- Start the admin panel: `cd admin_panel && uvicorn admin_panel.asgi:application`

## Updating the bot

1. `git pull`
2. `poetry install` to update dependencies
3. `cd admin_panel`
4. `python3 manage.py migrate`
5. `python3 manage.py collectstatic --no-input`
6. Restart the bot and admin panel