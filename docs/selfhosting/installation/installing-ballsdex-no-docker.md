# Installing Ballsdex without Docker

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

### git

[Git](https://git-scm.com/downloads) is needed to download and update the source code.

### uv

You will need our package manager `uv` to install the dependencies, manage Python versions and
virtual environments.

Follow the instructions [here](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)
to install uv on your system.

!!! tip
    Ballsdex requires Python 3.13 at least.

    If you don't have it installed, `uv` will install it for you, but you can make the installation
    lighter by installing Python 3.13 with your system's package manager.

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

1.  Download the bot's dependencies and install them in a virtual environment.

    ```bash
    uv sync
    ```
    !!! info
        If you don't have Python 3.13, it will also be downloaded for your virtual environment.

2.  Open the virtual environment where your dependencies are

    === "Linux/macOS"

        ```bash
        source .venv/bin/activate
        ```
    
    === "Windows (PowerShell)"

        ```ps1
        . .\.venv\Scripts\activate.ps1
        ```

3.  Export the `BALLSDEXBOT_DB_URL` environment variable with the link to Postgres you tested earlier.

    === "Linux/macOS"

        ```bash
        export BALLSDEXBOT_DB_URL=postgres://username:password@localhost:5432/database_name
        ```
    
    === "Windows (PowerShell)"

        ```ps1
        $Env.BALLSDEXBOT_DB_URL = 'postgres://username:password@localhost:5432/database_name'
        ```

4.  Check that the bot loads successfully. This should print the version number and exit.
    ```bash
    python3 -m ballsdex --version
    ```

5.  Create the default configuration file
    ```bash
    python3 -m ballsdex --reset-settings
    ```

6.  Open the `admin_panel` folder for the next steps
    ```bash
    cd admin_panel
    ```
7.  Initialize the database
    ```bash
    python3 manage.py migrate
    ```

8.  Initialize the admin panel
    ```bash
    python3 manage.py collectstatic --no-input
    ```
9.  Return to the previous directory for the next steps
    ```bash
    cd ..
    ```

## 5. Configure the bot

Follow [this section](installing-ballsdex.md#5-configure-the-bot) from the main tutorial to fill the base settings.

## 6. Run the bot

Then, run `python3 -m ballsdex` to start the bot! To shut it down, type Ctrl+C.

!!! tip
    There are multiple options available when running the bot, do `python3 -m ballsdex -h` to view them.

### Running the admin panel

1.  Open another shell with the virtualenv and the environment variables exported

    === "Linux/macOS"

        ```bash
        source .venv/bin/activate
        export BALLSDEXBOT_DB_URL=postgres://username:password@localhost:5432/database_name
        ```
    
    === "Windows (PowerShell)"

        ```ps1
        . .\.venv\Scripts\activate.ps1
        $Env.BALLSDEXBOT_DB_URL = 'postgres://username:password@localhost:5432/database_name'
        ```

2.  Start the admin panel
    ```bash
    cd admin_panel && uvicorn admin_panel.asgi:application
    ```
3.  Follow [this guide](../admin-panel/getting-started.md) afterwards

---

## Summary

Before running any command, do these:

=== "Linux/macOS"

    ```bash
    # open the bot's directory
    cd BallsDex-DiscordBot

    # activate the virtual environment
    source .venv/bin/activate

    # export the database env var
    export BALLSDEXBOT_DB_URL=postgres://username:password@localhost:5432/database_name
    ```

=== "Windows (PowerShell)"

    ```ps1
    # open the bot's directory
    cd BallsDex-DiscordBot

    # activate the virtual environment
    . .\.venv\Scripts\activate.ps1

    # export the database env var
    $Env.BALLSDEXBOT_DB_URL = 'postgres://username:password@localhost:5432/database_name'
    ```

Then

- Start the bot:
  ```bash
  python3 -m ballsdex
  ```
- Start the admin panel:
  ```bash
  cd admin_panel && uvicorn admin_panel.asgi:application
  ```

## Updating the bot

1.  Pull the new files.
    ```bash
    git pull
    ```
2.  Update dependencies
    ```bash
    uv sync
    ```
3.  Open the admin panel folder
    ```bash
    cd admin_panel
    ```
4.  Update the database schemas
    ```bash
    python3 manage.py migrate
    ```
5.  Update the admin panel static files
    ```bash
    python3 manage.py collectstatic --no-input
    ```
7.  Restart the bot and admin panel