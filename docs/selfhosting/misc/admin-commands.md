Ballsdex comes with commands to help moderators and administrators manage the bot.

## Using admin commands

These commands are hybrid, meaning they can both be used as a slash command (`/admin`) in
a selection of servers, and as a text command (`b.admin`) that can be used anywhere.

!!! note
    You can change the `b.` prefix in your global bot settings.

    You're also able to mention the bot to replace the prefix, which is useful if you have message
    content intent turned off: `@YourBot ping`

By default, only bot owners have access to the admin commands.

### Slash commands

To synchronize admin slash commands, use `b.admin syncslash` in the server of your choice.
Refresh your Discord client and commands should appear for administrators only by default.

!!! info
    To grant access to `/admin` to more roles, head to Server Settings -> Integrations ->
    <Your bot name> -> `/admin` and edit the permissions there.

You can then type `/admin` and see the list of commands unrolling.

### Text commands

If you can't use slash commands, for example if you're in a server other than your own and want
to spawn countryballs, you can use regular text commands.

With regular text commands, you can use the `b.help` command to show the available commands.

- `b.help` will show all commands available to you
- `b.help admin` will list all subcommands from admin
- `b.help admin history` will show all subcommands of this subcommand 
- `b.help admin history user` will show the full description of this command, with arguments

Let's have a look at this command. It has required arguments and optional arguments shown as
"flags". They follow a syntax similar to Discord slash commands, with the key and value separated
by a colon.

To execute that command on yourself, you'd do `b.admin history user @Yourself`. If you want to
filter the trade history with a second user, do `b.admin history user @Yourself user2:@Someone`.

Another example, if you want to spawn a shiny countryball, use `b.admin balls spawn special:Shiny`.
If you have to use arguments that would normally require an autocomplete converter (like specials
or countryballs), use the full name instead. If there are spaces in your name, just leave them:
`b.admin balls spawn countryball:Russian Empire atk_bonus:20`

!!! info
    `b.admin balls` will change to your configured slash command name. The flag `countryball:` will
    also change to your collectible name.

## Admin commands permissions

As the bot owner, you will always have full access to your bot. If you choose to move your
application to a Discord developer team, then all members of the team will share the same access.

Beyond that, permissions are handled with Django. You can create users on your admin panel
and share them a specific set of permissions, which will then grant them access to some commands.

### Creating a Django user

The process is slightly different whether you have enabled "Login with Discord" (OAuth2) or if
you're using password-based authentication.

=== "With OAuth2 enabled"

    Ask the user to authenticate to the admin panel. They will be denied at first, but the user
    will be created.

    !!! warning
        They will later have access to the admin panel, but only with the permissions you've chosen.

=== "With password authentication"

    1.  Open your admin panel and go to the users tab, then add a new user
    2.  Write the username and Discord user ID of your admin
    3.  Disable password-based authentication, unless you want to share them access later

Now you want to tick the "Is staff" checkbox of your user to grant them initial access to
the admin panel and the admin commands.

!!! warning
    If you want to remove an admin, **do not delete the user object**, instead untick the "Active"
    box. This will disable their account while preserving history.

### Granting permissions

Now you can edit your user and grant them individual permissions.

Each model of the bot has a set of 4 permissions: view, add, change, delete. These permissions
will be reflected on the admin panel and in the admin commands.

For example, to grant the permission to view the rarity list, you need "Can view countryball".
Spawning a countryball requires "Can add countryball instance". Viewing trades requires both
"Can view trade" and "Can view trade object".

To make things easier, you can also use permission groups. Give a set of permissions to a group
object, then grant these groups to users. For your convenience, two groups are pre-created:
"Administrator" and "Staff".

!!! tip
    If you were using Ballsdex v2, these groups will mostly reflect the permissions granted by
    `root-role-ids` and `admin-role-ids` respectively.

??? note "Default groups and permissions"

    <table><thead>
    <tr>
        <th></th>
        <th>Permission</th>
        <th>Staff</th>
        <th>Admin</th>
    </tr></thead>
    <tbody>
    <tr>
        <td rowspan="4">Ball</td>
        <td>View</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">Regime</td>
        <td>View</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">Economy</td>
        <td>View</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">Special</td>
        <td>View</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">BallInstance</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">BlacklistedID</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">BlacklistedGuild</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">BlacklistHistory</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    <tr>
        <td rowspan="4">Block</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">Friendship</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">GuildConfig</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">Player</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>✅</td>
    </tr>
    <tr>
        <td rowspan="4">Trade</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    <tr>
        <td rowspan="4">TradeObject</td>
        <td>View</td>
        <td>✅</td>
        <td>✅</td>
    </tr>
    <tr>
        <td>Change</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    <tr>
        <td>Add</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    <tr>
        <td>Delete</td>
        <td>❌</td>
        <td>❌</td>
    </tr>
    </tbody></table>

    You are free to edit those permissions after they were created.
