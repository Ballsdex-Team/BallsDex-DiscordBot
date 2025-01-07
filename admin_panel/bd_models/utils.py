def transform_media(path: str) -> str:
    return path.replace("/static/uploads/", "").replace(
        "/ballsdex/core/image_generator/src/", "default/"
    )
