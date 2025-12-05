from django.db import connection


def row_count_estimate(table_name: str, *, analyze: bool = True) -> int:
    """
    Estimate the number of rows in a table. This is *insanely* faster than querying all rows,
    but the number given is an estimation, not the real value.

    [Source](https://stackoverflow.com/a/7945274)

    Parameters
    ----------
    table_name: str
        Name of the table which you want to get the row count of.
    analyze: bool = True
        If the returned number is wrong (`-1`), Postgres hasn't built a cache yet. When this
        happens, an `ANALYSE` query is sent to rebuild the cache. Set this parameter to `False`
        to prevent this and get a potential invalid result.

    Returns
    -------
    int
        Estimated number of rows
    """
    with connection.cursor() as cursor:
        # returns as a tuple the number of rows affected (always 1) and the result as a list
        cursor.execute(f"SELECT reltuples AS estimate FROM pg_class where relname = '{table_name}';")
        record = cursor.fetchone()

        # Record type: https://magicstack.github.io/asyncpg/current/api/index.html#record-objects
        result = int(record[0])  # type: ignore
        if result == -1 and analyze is True:
            # the cache wasn't built yet, let's ask for an analyze query
            cursor.execute(f"ANALYZE {table_name}")
            return row_count_estimate(table_name, analyze=False)  # prevent recursion error

    return result
