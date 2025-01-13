from django.core.paginator import Paginator
from django.db import connection
from django.utils.functional import cached_property


class ApproxCountPaginator(Paginator):
    @cached_property
    def count(self):
        """Return the total number of objects, across all pages."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT reltuples AS estimate FROM pg_class where relname = "
                f"'{self.object_list.model._meta.db_table}';"  # type: ignore
            )
            result = int(cursor.fetchone()[0])
            if result < 100000:
                return super().count
            else:
                return result


def transform_media(path: str) -> str:
    return path.replace("/static/uploads/", "").replace(
        "/ballsdex/core/image_generator/src/", "default/"
    )
