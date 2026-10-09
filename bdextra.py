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
import tempfile
import subprocess
from pathlib import Path
from typing import NotRequired, TypedDict


class Package(TypedDict, total=True):
    location: str
    path: str
    enabled: bool
    editable: NotRequired[bool]


def discover_monorepo_packages(location: str) -> list[Package]:
    packages = []
    
    if location.startswith("git+"):
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                git_url = location.replace("git+", "", 1)
                
                if "==" in git_url:
                    git_url, version = git_url.rsplit("==", 1)
                    version = f"=={version}"
                else:
                    version = ""
                
                subprocess.run(
                    ["git", "clone", "--depth", "1", git_url, tmpdir],
                    capture_output=True,
                    check=True,
                    timeout=30,
                )
                
                repo_path = Path(tmpdir)
                git_location = f"git+{git_url}{version}"
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                warn(f"Failed to clone git repository: {location}")
                return packages
            else:
                repo_path = Path(location)
                git_location = location
    else:
        repo_path = Path(location)
        git_location = location
    
    if not repo_path.exists():
        warn(f"Path does not exist: {location}")
        return packages
    
    root_pyproject = repo_path / "pyproject.toml"
    
    for pyproject in repo_path.rglob("pyproject.toml"):
        if pyproject == root_pyproject:
            continue
        
        package_path = pyproject.parent.relative_to(repo_path)
        
        packages.append({
            "location": git_location,
            "path": str(package_path),
            "enabled": True,
            "editable": True,
        })
    
    return packages


def list_pip_packages(packages: list[Package]):
    print(
        " ".join(
            f"{'-e ' if x.get('editable', False) else ''}{x['location']}/{x['path']}"
            if x["path"]
            else f"{'-e ' if x.get('editable', False) else ''}{x['location']}"
            for x in packages
            if x["enabled"] and x["location"]
        )
    )


def main(toml_file: str):
    try:
        with open(toml_file, "rb") as f:
            contents = tomllib.load(f)
    except FileNotFoundError:
        warn("No extra.toml file found.")
        return
    
    packages: list[Package] = contents.get("ballsdex", {}).get("packages", [])
    
    expanded_packages = []
    for pkg in packages:
        if pkg.get("path") == "*":
            discovered = discover_monorepo_packages(pkg["location"])
            expanded_packages.extend(discovered)
        else:
            expanded_packages.append(pkg)
    
    list_pip_packages(expanded_packages)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ./bdextra.py <extra.toml>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
