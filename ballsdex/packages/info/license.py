import importlib.metadata
from typing import TYPE_CHECKING

import discord
from discord.ui import ActionRow, Button, Select, TextDisplay, button
from django.conf import settings

from ballsdex.core.discord import LayoutView, View
from ballsdex.core.translation import t
from ballsdex.core.utils.menus import ChunkedListSource, Menu, SelectFormatter

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


packages = importlib.metadata.packages_distributions()
extra_apps_dist: dict[str, importlib.metadata.Distribution] = {}
for app in settings.EXTRA_APPS:
    try:
        dist = importlib.metadata.distribution(packages[app][0])
        extra_apps_dist[dist.name] = dist
    except (KeyError, IndexError):
        pass


def get_package_select_options() -> list[discord.SelectOption]:
    options = []
    for package in extra_apps_dist.values():
        summary = package.metadata.get("Summary") or ""
        if len(summary) > 100:
            summary = f"{summary[:97]}..."
        options.append(discord.SelectOption(label=package.name, description=summary, value=package.name))
    return options


def get_license_files(dist: importlib.metadata.Distribution) -> list[importlib.metadata.PackagePath]:
    license_files: list[str] = dist.metadata.get_all("License-File") or []
    files: list[importlib.metadata.PackagePath] = []
    for file in dist.files or []:
        try:
            if file.parts[1] != "licenses":
                continue
        except IndexError:
            continue
        if file.name in license_files:
            files.append(file)
    return files


class ExtraLicenseView(LayoutView):
    header = TextDisplay(
        "This instance of Ballsdex is powered by 3rd-party packages whose information can be found below."
    )
    row = ActionRow()

    def __init__(self):
        super().__init__()
        # class-level TextDisplay content is resolved once at import time, before any
        # interaction exists - override it here so t() sees the viewing user's locale
        self.header.content = t(
            "This instance of Ballsdex is powered by 3rd-party packages whose information can be found below."
        )

    @row.select()
    async def extra_package_select(self, interaction: discord.Interaction["BallsDexBot"], select: Select):
        dist = extra_apps_dist[select.values[0]]
        text = f"## {dist.name} - {dist.version}\n"
        if summary := dist.metadata.get("Summary"):
            text += f"{summary}\n"
        if authors := dist.metadata.get_all("Author") or dist.metadata.get_all("Author-email"):
            text += t("Authors: {authors}\n" if len(authors) > 1 else "Author: {authors}\n").format(
                authors=", ".join(authors)
            )
        licenses = get_license_files(dist)
        if licenses:
            text += t("Licenses:" if len(licenses) > 1 else "License:")

        view = View()
        for item in (dist.metadata.get_all("Project-URL") or [])[:25]:
            label, link = item.split(", ")
            view.add_item(Button(label=label, url=link))
        await interaction.response.send_message(
            text,
            files=[discord.File(x.locate(), filename=f"{x}.txt" if not x.suffix else x.name) for x in licenses[:10]],
            ephemeral=True,
            view=view,
        )


class LicenseInfo(View):
    def __init__(self):
        super().__init__()
        # @button() labels are resolved once at class-body (import) time - override them here
        # so t() can see the locale of whoever ran the command that creates this view (/about)
        self.license_info.label = t("License info")
        self.extra_packages.label = t("3rd party packages")

    @button(label="License info")
    async def license_info(self, interaction: discord.Interaction["BallsDexBot"], _: Button):
        await interaction.response.send_message(
            t(
                "This bot is an instance of BallsDex-DiscordBot "
                "(hereinafter referred to as Ballsdex).\n"
                "Ballsdex is a free and open source application made available to the public and "
                "licensed under the MIT license. The full text of this license is attached below.\n"
            ),
            ephemeral=True,
            file=discord.File(
                get_license_files(importlib.metadata.distribution("ballsdex"))[0].locate(), filename="LICENSE.txt"
            ),
        )

    @button(label="3rd party packages")
    async def extra_packages(self, interaction: discord.Interaction["BallsDexBot"], _: Button):
        view = ExtraLicenseView()
        menu = Menu(
            interaction.client,
            view,
            ChunkedListSource(get_package_select_options()),
            SelectFormatter(view.extra_package_select),
        )
        await menu.init()
        await interaction.response.send_message(view=view, ephemeral=True)
