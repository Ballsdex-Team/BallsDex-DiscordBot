BD comes with utilities to manage the media that the bot uses.
## Media utilities
### Converting media 
You can run this command to convert your media to a new format. By default, it will use webp, but you can specify another format if you'd prefer something else—avif and webp typically have good filesizes.

=== "With Docker"

    ```bash
    docker compose exec admin-panel python3 -m django convert_media --target-format webp
    ```

=== "Without Docker"

    ```bash
    DJANGO_SETTINGS_MODULE=admin_panel.settings python3 -m django convert_media --target-format webp
    ```

### Removing unused media
You can run this command to remove media that your bot no longer uses (ie if you change the spawn image to something else)

!!! Warning
    Read the output of media to remove carefully! If you are using custom packages, or have assets in the media folder that are not reflected in the DB, they could be irreversibly lost!

=== "With Docker"

    ```bash
    docker compose exec admin-panel python3 -m django remove_unused_media
    ```

=== "Without Docker"

    ```bash
    DJANGO_SETTINGS_MODULE=admin_panel.settings python3 -m django remove_unused_media
    ```
