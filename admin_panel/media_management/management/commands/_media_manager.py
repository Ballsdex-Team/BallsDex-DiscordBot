from pathlib import Path

from bd_models.models import Ball, Economy, Regime, Special
from django.db import models


def all_media() -> list[tuple[models.Model, Path, str]]:
    """Returns all media in the DB in the form of a list of tuples containing
    a instance of a model, the ImageField containing the media, and the name of the attribute
    that can be used to find that media"""

    media_types: dict[type[models.Model], list[str]] = {
        Ball: ["collection_card", "wild_card"],
        Special: ["background"],
        Economy: ["icon"],
        Regime: ["background"],
    }
    medias: list[tuple[models.Model, Path, str]] = []

    for model_type, media_attrs in media_types.items():
        for model_instance in model_type.objects.all():  # type: ignore
            for media_attr in media_attrs:
                path = Path(getattr(model_instance, media_attr).path)
                medias.append((model_instance, path, media_attr))

    return medias


def boolean_input(question, default=None) -> bool:
    query = f"{question} [{'y/n' if default is None else ('Y/n' if default else 'y/N')}]: "
    result = None
    while not result:
        result = input(query)
        if result == "" and default is not None:
            return default
        if result.lower() in ["y", "yes", "yeah", "yay", "ya"]:
            return True
        elif result.lower() in ["n", "no", "nay", "nah"]:
            return False
        else:
            result = None
            continue

    # Shouldn't be possible to get here but this appeases pyright
    return False
