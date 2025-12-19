# Writing custom packages

This tutorial will explain you how to extend Ballsdex with additional commands and features
the recommended way.

## Getting a good developer environment

Before getting to coding, you want to have a good environment to code and test quickly.

1.  Download [Visual Studio Code](https://code.visualstudio.com/). Make sure to check the
    "Add to PATH" option when prompted.

    If you're on Windows, install the
    [WSL extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl) as well.
    
    !!! info
        You can use the editor of your choice, but Ballsdex is pre-configured for VScode and will
        give you the best out-of-the-box experience.

2.  Install and configure Ballsdex locally. I recommend that you follow the
    [Dockerless install](/selfhosting/installation/installing-ballsdex-no-docker/) to enable
    VScode's Python debugger, but Docker is also fine.

    1.  If you have followed the Docker installation, we will also configure a local environment
        for autocompletion and editor experience.
        First, [install uv](https://docs.astral.sh/uv/getting-started/installation/)
    2.  Open a terminal and `cd` into the Ballsdex folder
    3.  Run `uv sync --all-extras`

        You may need to run this command from time to time if dependencies are updated.

3.  Open a terminal, `cd` into the Ballsdex folder and run `code .` to open Visual Studio Code.
    This also works inside WSL!

4.  Now you can run the bot in debug mode

    === "With Docker"

        First, let's create a new file called `docker-compose.override.yml` to enable a few
        developer options:

        ```yml
        services:
          bot:
            command: python3 -m ballsdex --dev --debug
            environment:
              - "DJANGO_SETTINGS_MODULE=admin_panel.settings.dev"
          admin-panel:
            environment:
              - "DJANGO_SETTINGS_MODULE=admin_panel.settings.dev"
        ```

        Then you can start the bot with the following command

        ```sh
        docker compose down  # clear up old containers and load the new file
        docker compose up --watch
        ```

        The `--watch` option will enable live-reloading of your code inside Docker!
    
    === "Without Docker"

        ```sh
        export DJANGO_SETTINGS_MODULE=admin_panel.settings.dev
        
        # run the bot like this
        python3 -m ballsdex --dev --debug

        # and the admin panel like this
        uvicorn --reload admin_panel.asgi:application
        ```

        You can also use VScode's debugger by pressing F5, profiles are already registered!

That's it, you're now setup to develop on Ballsdex!

## Creating your package

You will be writing a standalone pip-installable
[Python package](https://packaging.python.org/en/latest/tutorials/packaging-projects/). This
means your code will live in its own repository, but for now we'll be coding in a special
folder that makes development easier.

1.  Create a folder in `extra`, this will be your repository. For this example, let's call our
    repository `my_cool_repo`
    ```sh
    mkdir extra/my_cool_repo
    ```
2.  Since you are writing a full Python package, you need a `pyproject.toml` file. Create the file
    `extra/my_cool_repo/pyproject.toml` and place the following contents

    ```toml
    [project]
    name = "my_cool_repo"
    version = "1.0.0"

    dependencies = [
        # you can require a specific version of ballsdex here
        "ballsdex>=3.0.0",
    ]
    ```

    You can customize this file later to include extra dependencies and more[^1]

    [^1]: [Python packaging](https://packaging.python.org/en/latest/tutorials/packaging-projects/)

3.  Now we need to create a Django application. I will name mine `my_cool_app`

    === "With Docker"
        ```sh
        docker compose run --rm migration django-admin startapp my_cool_app /code/extra/my_cool_repo/my_cool_app
        ```

    === "Without Docker"
        ```sh
        export DJANGO_SETTINGS_MODULE="admin_panel.settings.dev"
        cd extra/my_cool_repo
        django-admin startapp my_cool_app
        ```

    This will create a new folder `my_cool_app` with the following files:
    -   `__init__.py`: mandatory, do not remove
    -   `admin.py`: useful if you want to extend the admin panel
    -   `apps.py`: mandatory, do not remove
    -   `models.py`: this is where you want to put your custom models if you need to save data
    -   `tests.py`: unused, can be removed
    -   `views.py`: unless you're writing web pages (why), can be removed

## Adding a discord.py extension

The reason why you're here is most likely to write custom
[discord.py extension](https://discordpy.readthedocs.io/en/latest/ext/commands/extensions.html).
This will allow you to write your own commands and listeners.

1.  Let's call our extension `my_cool_ext`. We will create the following files:

    ```py title="extra/my_cool_repo/my_cool_app/my_cool_ext/cog.py"
    from typing import TYPE_CHECKING

    from discord import app_commands
    from discord.ext import commands

    if TYPE_CHECKING:
        from ballsdex.core.bot import BallsDexBot


    class YourCog(commands.Cog):
        def __init__(self, bot: "BallsDexBot"):
            self.bot = bot

        @commands.command()
        async def hello(self, ctx: commands.Context["BallsDexBot"]):
            await ctx.send("Hello World!")
    ```

    ```py title="extra/my_cool_repo/my_cool_app/my_cool_ext/__init__.py"
    from typing import TYPE_CHECKING

    from .cog import YourCog

    if TYPE_CHECKING:
        from ballsdex.core.bot import BallsDexBot


    async def setup(bot: "BallsDexBot"):
        await bot.add_cog(YourCog(bot))
    ```

2.  You now need to let your app know that it supports a discord.py extension, and where it's
    located. Open `extra/my_cool_repo/my_cool_app/apps.py` and add the following line:

    ```py hl_lines="6"
    from django.apps import AppConfig


    class MyCoolAppConfig(AppConfig):
        name = "my_cool_app"
        dpy_package = "my_cool_app.my_cool_ext"
    ```

That's it, your discord.py extension is now ready with a minimal command to test if it loaded
properly!

## Loading your code

For now we will only be looking at loading your code from a developer's perspective.

=== "With Docker"

    1.  Create the file `config/extra.toml` and write the following contents

        ```toml
        [[ballsdex.packages]]
        location = "/code/extra/my_cool_repo"
        path = "my_cool_app"
        enabled = true
        editable = true
        ```

    2.  Install your package with `docker compose build` (you should only need to do this once)
    3.  Launch the bot with `docker compose up --watch`

=== "Without Docker"

    1.  Create the file `config/extra.toml` and write the following contents

        ```toml
        [[ballsdex.packages]]
        location = ""  # this only matters for Docker
        path = "my_cool_app"
        enabled = true
        editable = true
        ```
    2.  Make sure your uv env is activated
    3.  Install your package with `uv pip install -e extra/my_cool_repo`
    4.  Launch the bot!

You should notice this appearing in your bot's logs if successful:
```
2025-12-16 14:32:17 INFO     ballsdex.core.bot Packages loaded: admin, balls, guildconfig, countryballs, info, players, trade, my_cool_ext
```

Test the `b.hello` command somewhere in Discord and see if the bot responds!

!!! tip
    You can use `b.reload my_cool_ext` to live-reload new changes applied to your code without
    restarting the bot.

!!! info "Useful links"

    - [discord.py Cogs](https://discordpy.readthedocs.io/en/latest/ext/commands/cogs.html)
    - [discord.py commands](https://discordpy.readthedocs.io/en/latest/ext/commands/commands.html)
    - [discord.py interactions (app commands and buttons)](https://discordpy.readthedocs.io/en/latest/interactions/api.html)

## Using the database

The point of having a Django app is to let you write your own models and use them in your
application. Let's write a few example models.

Let's suppose our app wants to add a profile command, which lets the player define a title,
a bio, countries they're open for trade, and their best friend. We need two tables:

-   `Profile` which stores the title, bio and best friend
-   `LFBall` which stores which countries a player may be looking for

A possible model definition would be the following:

```py title="models.py"
from django.db import models

from bd_models.models import Ball, Player, Special


class Profile(models.Model):
    # link the profile to exactly one player
    # if the player is deleted, the profile will be deleted too
    player = models.OneToOneField(Player, on_delete=models.CASCADE)

    title = models.CharField(max_length=32)
    bio = models.TextField()  # uncapped in length

    # this field will be optional, if the other player is deleted, then the favorite is set back to null
    # it's a ForeignKey (OneToMany) instead of a OneToOneField, since a player may be the favorite friend of multiples
    favorite_friend = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True)

    class Meta:
        constraints = [
            # a simple restriction to ensure the player doesn't set themselves as favorite friend
            models.CheckConstraint(condition=~models.Q(player=models.F("favorite_friend")), name="friend_neq_player")
        ]


class LFBall(models.Model):
    # this time we will be using a ForeignKey as one player may have multiple LFBall entries
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    # same for the ball the player is looking for
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE)

    # we will also add an optional "special" specifier
    # if a special gets deleted, the LF entry should also be removed
    special = models.ForeignKey(Special, on_delete=models.CASCADE, null=True)
```

Once this code has been written, we have to write a migration, it's a generated file that will
define how to populate the database the first time your app is loaded or updated.

=== "With Docker"

    ```sh
    docker compose run --rm migration django-admin makemigrations my_cool_app
    ```

=== "Without Docker"

    ```sh
    django-admin makemigrations my_cool_app
    ```

This should generate the following, along with a new file in
`extra/my_cool_repo/my_cool_app/migrations/0001_initial.py`
```ansi
Migrations for 'test_app':
  /code/extra/test_app/test_app/migrations/0001_initial.py
    + Create model LFBall
    + Create model Profile
```

Then you simply need to run migrations as usual (done automatically in Docker). If you need to edit
your models in future versions, just generate more migrations (and don't delete the previous ones).

It can then be used in your code like this:

```py
...

from bd_models.models import Player

from ..models import Profile, LFBall


class YourCog(commands.Cog):
    ...

    @app_commands.command()
    async def profile(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User | None = None):
        user = user or interaction.user
        try:
            player = await Player.objects.aget(discord_id=user.id)
            # pre-fetch the favorite friend's details
            profile = await Profile.objects.aget(player=player).prefetch_related("favorite_friend")
        except Player.DoesNotExist:
            await interaction.response.send_message("No such player.", ephemeral=True)
            return
        except Profile.DoesNotExist:
            await interaction.response.send_message("No profile associated.", ephemeral=True)
            return

        text = (
            f"# {user.name}'s profile\n"
            f"-# {profile.title}\n"
            f"{profile.bio}\n"
        )
        if profile.favorite_friend:
            text += f"Favorite friend: <@{profile.favorite_friend.discord_id}>\n"
        
        lf_query = LFBall.objects.filter(player=player)
        if await lf_query.aexists():
            text += f"## Looking for\n"
            async for ball in lf_query:
                text += f"- {ball.country}\n"

        await interaction.response.send_message(text)
```

Please note that all Django queries must be using the asynchronous version, using synchronous
version will crash.

If you need to fetch the object behind a `ForeignKey`, don't forget to use
[`prefetch_related`](https://docs.djangoproject.com/en/6.0/ref/models/querysets/#prefetch-related)
or this will trigger an additional query, and fail because it's not asynchronous.

!!! info "Useful links"
    - [Django ORM tutorial](https://docs.djangoproject.com/en/6.0/topics/db/queries/)
    - [Django queries reference](https://docs.djangoproject.com/en/6.0/ref/models/querysets/)


### Using the admin panel

You can also make use of the admin panel through the `admin.py` file. The most basic configuration
will look like this:

```py title="admin.py"
from django.contrib import admin

from .models import LFBall, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    pass


@admin.register(LFBall)
class LFBallAdmin(admin.ModelAdmin):
    pass
```

Then loading the admin panel will display your app:
![](image.png)
![](image-1.png)

However, be careful with large models such as `Player` or `BallInstance`, they will load *all*
items in the admin panel. You can avoid this with `autocomplete_fields`:

```py
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    autocomplete_fields = ("player", "favorite_friend")


@admin.register(LFBall)
class LFBallAdmin(admin.ModelAdmin):
    autocomplete_fields = ("player", "ball")
```

There are many more options, feel free to take a look at
[the documentation](https://docs.djangoproject.com/en/6.0/ref/contrib/admin/) or how I
wrote the admin views in `admin_panel/bd_models/admin/`.

## Publishing your package

Once your package is ready, you can choose to publish it!

1.  Make a repository of your folder, and commit your changes

    ```sh
    cd extra/my_cool_repo
    git init
    ```

2.  Create a `.gitignore` to avoid pushing unwanted files. A minimal one may contain:

    ```gitignore
    # Python stuff
    *.pyc
    __pycache__
    *.egg-info
    ```

3.  For your project to be open source and allow others to use it, you need a license.

    Visit [https://choosealicense.com/]() and put the contents of your license in a file named
    `LICENSE` at the root of your repository (`extra/my_cool_repo/LICENSE`).

4.  Write a cool `README.md` describing your app.

5.  Review the contents of your `pyproject.toml` and add some metadata. Don't forget to put the
    license.

    ```toml hl_lines="5-11 16 20-22"
    [project]
    name = "my_cool_repo"
    version = "1.0.0"

    description = "A very nice repository"
    license = "MIT"  # replace with your own license
    license-files = ["LICENSE"]
    authors = [
        { name = "laggron42", email = "laggron42@ballsdex.com" },
    ]
    readme = "README.md"

    dependencies = [
        # you can require a specific version of ballsdex here
        "ballsdex>=3.0.0",
        # and extra dependencies if needed
    ]

    [project.urls]
    # put your own links here
    # https://packaging.python.org/en/latest/specifications/well-known-project-urls/#well-known-project-urls
    Homepage = "https://github.com/username/repo-name"
    ```

    Check out the [`pyproject.toml` documentation](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#writing-pyproject-toml)
    to read more about what you can put there.

    !!! info
        The `name`, `version`, `description`, `license-files`, `authors` and `project.urls` fields
        will be displayed to all users via the core `/about` command.

6.  Commit your code.

    ```sh
    git add --all
    # review that only the files you want to push are listed
    git status
    # and commit
    git commit -m "First commit"
    ```

    !!! warning
        You may need to configure your username and email if this is your first time using git.

7.  Create an online repository on the host of your choice (Github, Gitlab, ...) and push your
    repo. I will assume that my repository's URL is `https://github.com/laggron42/my_cool_repo.git`

    ```sh
    git remote add origin https://github.com/laggron42/my_cool_repo.git
    git push -u origin master
    ```

All done, your project is now published!

If you need to update your project in the future, don't forget to update the `version` in your
`pyproject.toml`.

### Installing your package as a user

Any user wishing to install your package must simply add the following contents in their
`config/extra.toml` file:

```toml
[[ballsdex.packages]]
location = "git+https://github.com/laggron42/my_cool_repo.git==1.0.0"
path = "my_cool_app"
enabled = true
```

It's important that `editable` is omitted or set to `false`, it will only work for the developer.
