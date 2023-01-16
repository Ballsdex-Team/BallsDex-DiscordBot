import sys

import rich
import discord
import logging
import logging.handlers

from rich.highlighter import Highlighter
from rich.logging import RichHandler as DefaultRichHandler
from rich.style import Style
from rich.theme import Theme
from rich.traceback import PathHighlighter, Traceback
from rich.text import Text, TextType
from rich._log_render import LogRender as DefaultLogRender

from types import ModuleType
from datetime import datetime
from typing import Iterable, List, Optional, TYPE_CHECKING, Union, Callable

if TYPE_CHECKING:
    from rich.console import Console, ConsoleRenderable, RenderableType
    from rich.table import Table

discord.voice_client.VoiceClient.warn_nacl = False  # disable PyNACL warning


class LogRender(DefaultLogRender):
    def __init__(self):
        self._last_time: Optional[Text] = None

    def __call__(
        self,
        console: "Console",
        renderables: Iterable["ConsoleRenderable"],
        logger: str,
        log_time: Optional[datetime] = None,
        time_format: Optional[Union[str, Callable[[datetime], Text]]] = None,
        level: TextType = "",
    ) -> "Table":
        from rich.containers import Renderables
        from rich.table import Table

        output = Table.grid(padding=(0, 1))
        output.expand = True
        output.add_column(style="log.time")
        output.add_column(style="log.level", width=8)
        output.add_column(ratio=1, style="log.message", overflow="fold")
        output.add_column(style="log.path")
        row: List["RenderableType"] = []

        log_time = log_time or console.get_datetime()
        time_format = time_format or self.time_format
        if callable(time_format):
            log_time_display = time_format(log_time)
        else:
            log_time_display = Text(log_time.strftime(time_format))
        if log_time_display == self._last_time:
            row.append(Text(" " * len(log_time_display)))
        else:
            row.append(log_time_display)
            self._last_time = log_time_display

        row.append(level)
        row.append(Renderables(renderables))

        logger_name = Text()
        logger_name.append(logger)
        row.append(logger_name)

        output.add_row(*row)
        return output


class RichHandler(DefaultRichHandler):
    def __init__(
        self,
        level: Union[int, str] = logging.NOTSET,
        console: Optional["Console"] = None,
        *,
        enable_link_path: bool = True,
        highlighter: Optional[Highlighter] = None,
        markup: bool = False,
        rich_tracebacks: bool = False,
        tracebacks_width: Optional[int] = None,
        tracebacks_extra_lines: int = 3,
        tracebacks_theme: Optional[str] = None,
        tracebacks_word_wrap: bool = True,
        tracebacks_show_locals: bool = False,
        tracebacks_suppress: Iterable[Union[str, ModuleType]] = (),
        locals_max_length: int = 10,
        locals_max_string: int = 80,
        keywords: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            level,
            console,
            enable_link_path=enable_link_path,
            highlighter=highlighter,
            markup=markup,
            rich_tracebacks=rich_tracebacks,
            tracebacks_width=tracebacks_width,
            tracebacks_extra_lines=tracebacks_extra_lines,
            tracebacks_theme=tracebacks_theme,
            tracebacks_word_wrap=tracebacks_word_wrap,
            tracebacks_show_locals=tracebacks_show_locals,
            tracebacks_suppress=tracebacks_suppress,
            locals_max_length=locals_max_length,
            locals_max_string=locals_max_string,
            keywords=keywords,
        )
        self._log_render = LogRender()

    def render(
        self,
        *,
        record: logging.LogRecord,
        traceback: Optional[Traceback],
        message_renderable: "ConsoleRenderable",
    ) -> "ConsoleRenderable":
        level = self.get_level_text(record)
        time_format = None if self.formatter is None else self.formatter.datefmt
        log_time = datetime.fromtimestamp(record.created)

        return self._log_render(
            self.console,
            [message_renderable] if not traceback else [message_renderable, traceback],
            record.name,
            log_time=log_time,
            time_format=time_format,
            level=level,
        )


def init_logger(disable_rich_logging: bool = False, debug: bool = False):
    log = logging.getLogger("ballsdex")
    log.setLevel(logging.DEBUG)
    dpy_log = logging.getLogger("discord")
    dpy_log.setLevel(logging.INFO)
    tortoise_log = logging.getLogger("tortoise")
    tortoise_log.setLevel(logging.INFO)
    loggers = (log, dpy_log, tortoise_log)

    rich_console = rich.get_console()
    rich.reconfigure(tab_size=4)
    rich_console.push_theme(
        Theme(
            {
                "log.time": Style(dim=True),
                "logging.level.debug": Style(color="cyan"),
                "logging.level.info": Style(color="green"),
                "logging.level.warning": Style(color="yellow"),
                "logging.level.error": Style(color="red"),
                "logging.level.critical": Style(color="red", bold=True),
                "repr.number": Style(color="cyan"),
                "repr.url": Style(underline=True, italic=True, bold=False, color="blue"),
            }
        )
    )
    rich_console.file = sys.stdout
    PathHighlighter.highlights = []

    formatter = logging.Formatter(
        "[{asctime}] {levelname} {name}: {message}", datefmt="%Y-%m-%d %H:%M:%S", style="{"
    )

    # file logger
    file_handler = logging.handlers.RotatingFileHandler(
        "ballsdex.log", maxBytes=8**7, backupCount=8
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    for log in loggers:
        log.addHandler(file_handler)

    # stdout logger
    if disable_rich_logging:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
    else:
        rich_formatter = logging.Formatter("{message}", datefmt="[%X]", style="{")
        stream_handler = RichHandler(rich_tracebacks=True, tracebacks_extra_lines=2)
        stream_handler.setFormatter(rich_formatter)
    level = logging.DEBUG if debug else logging.INFO
    stream_handler.setLevel(level)
    for log in loggers:
        log.addHandler(stream_handler)
