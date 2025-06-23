Ballsdex now uses Django to power its admin panel. It is a much more powerful, stable and efficient system than the old fastapi admin panel.

# Starting the panel

If you are running Docker, the panel may already be running. Just do `docker compose up -d admin-panel` to start if it's not running.

Without docker, the command to start the admin panel is `cd admin_panel && poetry run python3 manage.py migrate && poetry run python3 manage.py collectstatic --no-input && poetry run uvicorn admin_panel.asgi:application`

The panel will then be accessible at [http://localhost:8000](http://localhost:8000)

# Configuring the panel

Before using this panel, you must configure a way to login. You can either enable the "Login with Discord" button, or use accounts with a password (or both).

## Using local accounts

The easiest way to login is to create accounts with a login and a password. Run the commands
below and follow the prompts.

=== "With Docker"

    ```bash
    docker compose up -d admin-panel
    docker compose exec admin-panel python3 manage.py createsuperuser
    ```

=== "Without Docker"

    ```bash
    cd admin_panel && poetry run python3 manage.py createsuperuser
    ```

Then you can login using the chosen credentials at http://localhost:8000. Additional accounts can be created from the admin panel.

## Using Discord OAuth2 (login with Discord)

This will only let the bot owner access the admin panel when logged in, no need to remember any password.

1. Go to the [Discord developer portal](https://discord.com/developers) and click on your application
2. Click the "OAuth" tab
3. Copy the application ID and paste it in your `config.yml` file, next to `client-id: ` (don't forget to leave a space after the colon)
4. Generate your application secret and paste it in the config file, next to `client-secret: `
5. Add a new redirect URI: `http://localhost:8000/complete/discord/` (the trailing slash is important)
6. Save the changes

!!! danger
    Keep your application secret hidden at all times, it must never be shared (like your bot token)! If you have suspicion this file was leaked, immediately reset it in your developer portal.

In addition, you can also create a webhook for notifications from the admin panel, such as a new user registering or more in the future. This is optional but recommended:

1. Go to a Discord text channel that's only viewable by you or other admins
2. Open the settings, then the integrations menu, then create a Webhook
3. Copy the URL, and paste it next to `webhook-url: ` in the config file

You should now be good to go. Run `docker compose up -d admin-panel` to start the admin panel (**if it was already running, restart it**), and open http://localhost:8000/ in your browser. Click the "Login with Discord" button and follow the steps. If you are the bot owner, then you will have the superuser status automatically assigned.

!!! success "Developer teams"
    If the application is owned by a team, set `team-members-are-owners` to true in the config file, otherwise you won't get access.

# Using the panel

Once you are logged in, you will see the panel's home page, with multiple options appearing on the sidebar.

The "Authentication and authorization" section should be ignored unless you serve the panel on the internet, it contains the user accounts and permission groups. "Python social auth" should also be ignored and not tampered with, it contains the Discord OAuth2 data that allows you to login.

The "Ballsdex models" section is what you are looking for, it has all the models from the bot:

- `BallInstances` represents instances of a ball that were obtained by a player. You can use that to give balls to players, delete then, modify attributes or look at its trade history. Searching via hexadecimal ID is supported.
- `Balls` is where you create your countryballs (or whatever your bot is themed after). It's the first thing you want to visit, more details below.
- `Economies` is for the little icon on the top right of cards. By default, you'll have communist and capitalist economies (but you can set none).
- `Players` contains the list of all players. You can change their settings, view their inventory, trade history, or latest catches (to hunt for farmers). Searching by Discord ID works.
- `Regimes` represents the backgrounds of your cards. Each ball must have a regime assigned. By default you have 3 available: democracy, dictatorship and union.
- `Specials` is for making some ball instances special with a custom background and a special catching phrase. They can have start and end dates for limited-time events, a custom phrase to display when caught, and ofc the special background to apply. Using a rarity of 0 renders it unobtainable by the public, but can still be applied by admins.
- `Trades` has the list of all trades performed. Clicking on a trade will show all of its contents.

!!! info
    The admin panel will always use the Ballsdex vocabulary (countryballs). If you have set a custom name for your bot or your collectibles, don't worry, they will be used throughout the bot itself.

## Creating your first countryball

Click the "Add" button next to "Balls", or click the "Add ball" button on the top left if you have opened the balls tab. You will be presented with a form to fill. If the label on the left side is bold, it means a value is required, otherwise it's optional.

### Base fields

- `Country`: The name of your collectible
- `Health` and `Attack`: Base stats, they will be applied a +/-20% bonus when caught (customizable in `config.yml`)
- `Rarity`: Defines how rare the ball will be when spawning. Setting a rarity of 0 will make the ball unspawnable (but it will still appear in completion and user commands!). Check [this page](https://github.com/Ballsdex-Team/BallsDex-DiscordBot/wiki/Rarity-mechanism) to understand how rarity works.
- `Emoji ID`: The ID of your ball's emoji. You can upload application emojis from the [Discord developer portal](https://discord.com/developers/applications), click your bot and go to the "Emojis" tab. Emojis from servers shared by the bot are also supported.
- `Economy`: The icon at the top right of your card. You can leave this blank.
- `Regime`: Sets the background of your card, this is required.

### Assets

Then you have a section for assets. You must upload two files:

- `Wild card`: The file that will be sent in the chat when the ball spawns. It's usually a file, but you can upload a video, a GIF, an mp3... anything that embeds in Discord.
- `Collection card`: The image used when generating the card. The size of the image should be 1359x731, or a ratio of approximatively 18:10 (it is automatically resized and centered).
- `Credits`: This is where you credit the artists of both uploaded assets.

!!! danger
    ⚠️ **You must have the permission to use the images you are uploading!!** ⚠️
    
    Not everything you find on Google is free to use, unless it is clearly labelled as **Creative commons** (there is a filter in Google images for that).  
    Unless you are the artist, you must have explicit permission from the artist to use their assets in your bot. This may come at the cost of a license.
    
    **Violating licenses exposes you to a DMCA complaint, which can lead to both your bot and your own account getting banned from Discord.**
    
    All art used by Ballsdex is licensed to the Ballsdex Team and cannot be reused by other bots without permission from their artists. However, the MIT-licensed files included in the bot repository (such as the default backgrounds) are free to use.

### Ability

Finally, you have two fields, `Capacity name` and `Capacity description`, which actually refer to the ability name and description. *My english wasn't as good back then, and it's hard to change it now.*

### Advanced

If you unroll this section, you will find a few settings you probably don't need at first.

- `Enabled`: If unticked, the ball will not spawn (regardless of rarity), appear in `/balls completion` or appear in user-facing commands. You can still spawn it or give it manually using `/admin` commands or this panel.
- `Tradeable`: If unticked, any instance of this ball won't be tradeable at all.
- `Short Name`: When the name is so long that it overflows in the card, you can use this field to choose a shorter name that will be only used in card generation. This is limited to 12 characters.
- `Catch names`: A list of additional names, lowercased and separated by semicolons, that can be used to catch this countryball when spawned. The main name remains usable for catching. It is important to not leave any space between the semicolons or this will break.
- `Translations`: This has the exact same effect as `Catch names`. The reason this exists is to automatically update translations without breaking additional catch names (like abbreviations).
- `Capacity logic`: A JSON field of extra data, currently unused. This is planned to be used for the battle system.

----

Once you have filled everything needed, click the "Save and continue editing" button, this will show you a preview of what the card looks like in the sidebar! Once you're satisfied with the result, go to Discord and send `b.reloadcache` to your bot, and your ball should start spawning.

!!! success
    It is always a good idea to test spawn your ball with `/admin balls spawn` and ensure it works as intended.

!!! tip
    You can edit rarities and enable balls in bulk from the list of balls. There is a save button at the end.

!!! failure "Caution"
    Deleting a ball will delete all ball instances associated. This may be an extremely slow operation, and it is not reversible!

## Creating your first special

A "special" is a way to override the attributes of a ball instance to make it special. When a ball is caught, it may gain an active special based on its rarity. By default, you will have one special named "Shiny" with a chance of 1/2048 to happen. If you do not want shinies on your bot, it is safe to delete it from this panel.

Specials can have a start and end date to indicate that it will be limited in time, but you can also omit those to have a special active permanently.

!!! warning
    If you want to end a special from being active, **do not delete it** as all ball instances will lose the special attribute. Instead, configure the end date or set its rarity to 0.

### Base fields

- `Name`: The name of this special
- `Catch phrase`: A sentence that will appear when a caught ball gets this special, for example "It's a shiny countryball"
- `Rarity`: Defines the odds of getting that special. **This must be between 0 and 1 included.** Check [this page](https://github.com/Ballsdex-Team/BallsDex-DiscordBot/wiki/Rarity-mechanism) to understand how rarity works.
- `Emoji`: The emoji to place next to the ball instance to identify it. This must be a single unicode emoji, Discord emojis cannot be used for technical reasons.
- `Background`: The new background to apply, this must be **precisely** 1428x2000 pixels. If the dimensions are off, the card generation will break.
- `Start date` and `End date`: Optional date range to keep this event active. Both values are optional. Not setting a start date will make an event active immediately upon reload.

### Advanced

- `Tradeable`: Similar to the Ball setting, unticking this renders all balls with this special untradeable.
- `Hidden`: If ticked, this special won't appear in user-facing commands (such as slash command autocompletion)

Don't forget to run `b.reloadcache` to refresh your modifications!

----

Creating balls and specials are the most important aspect of the admin panel, once you understood this you should be good to go.

There are many more tools this admin panel offers, but you should be able to understand by yourself how they work by exploring!

!!! example "Important"
    If you want to expose your admin panel online, please follow [this tutorial](./exposing-to-internet.md)!  
    It's important that you do not expose the website yourself, the default configuration is insecure.