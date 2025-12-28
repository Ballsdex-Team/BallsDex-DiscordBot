#!/usr/bin/env python3
"""
This file is used to parse 3rd party packages to install and configure.

No dependencies are needed for this, it can be ran in standalone Python 3.11.
"""

import sys
from warnings import warn

if sys.version_info.major < 3 or sys.version_info.minor < 11:
    print("You need Python 3.11+ to run this.", file=sys.stderr)
    sys.exit(1)

import tomllib
from typing import TypedDict


class Package(TypedDict, total=True):
    location: str
    path: str
    enabled: bool
    editable: bool


def list_pip_packages(packages: list[Package]):
    print(
        " ".join(f"{'-e ' if x['editable'] else ''}{x['location']}" for x in packages if x["enabled"] and x["location"])
    )


def main(toml_file: str):
    try:
        with open(toml_file, "rb") as f:
            contents = tomllib.load(f)
    except FileNotFoundError:
        warn("No extra.toml file found.")
        return
    packages: list[Package] = contents.get("ballsdex", {}).get("packages", [])
    list_pip_packages(packages)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ./bdextra.py <extra.toml>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
