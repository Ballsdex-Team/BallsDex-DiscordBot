from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Optional, Union
import parsedatetime as pdt
from dateutil.relativedelta import relativedelta
from .formats import plural, human_join, format_dt as format_dt
import discord
from discord.ext import commands
from discord import app_commands
import re

# Monkey patch mins and secs into the units.
units = pdt.pdtLocales['en_US'].units
units['minutes'].append('mins')
units['seconds'].append('secs')

if TYPE_CHECKING:
    from typing_extensions import Self


class ShortTime:
    compiled = re.compile(
        """
           (?:(?P<years>[0-9])(?:years?|y))?                      # e.g. 2y
           (?:(?P<months>[0-9]{1,2})(?:months?|mon?))?            # e.g. 2months
           (?:(?P<weeks>[0-9]{1,4})(?:weeks?|w))?                 # e.g. 10w
           (?:(?P<days>[0-9]{1,5})(?:days?|d))?                   # e.g. 14d
           (?:(?P<hours>[0-9]{1,5})(?:hours?|hr?s?))?             # e.g. 12h
           (?:(?P<minutes>[0-9]{1,5})(?:minutes?|m(?:ins?)?))?    # e.g. 10m
           (?:(?P<seconds>[0-9]{1,5})(?:seconds?|s(?:ecs?)?))?    # e.g. 15s
        """,
        re.VERBOSE,
    )

    discord_fmt = re.compile(r'<t:(?P<ts>[0-9]+)(?:\:?[RFfDdTt])?>')

    dt: datetime.datetime

    def __init__(
        self,
        argument: str,
        *,
        now: Optional[datetime.datetime] = None,
        tzinfo: datetime.tzinfo = datetime.timezone.utc,
    ):
        match = self.compiled.fullmatch(argument)
        if match is None or not match.group(0):
            match = self.discord_fmt.fullmatch(argument)
            if match is not None:
                self.dt = datetime.datetime.fromtimestamp(int(match.group('ts')), tz=datetime.timezone.utc)
                if tzinfo is not datetime.timezone.utc:
                    self.dt = self.dt.astimezone(tzinfo)
                return
            else:
                raise commands.BadArgument('Invalid time provided.')

        data = {k: int(v) for k, v in match.groupdict(default=0).items()}
        now = now or datetime.datetime.now(datetime.timezone.utc)
        self.dt = now + relativedelta(**data)
        if tzinfo is not datetime.timezone.utc:
            self.dt = self.dt.astimezone(tzinfo)

    @classmethod
    async def convert(cls, interaction: discord.Interaction, argument: str) -> Self:
        tzinfo = datetime.timezone.utc
        reminder = interaction.bot.reminder # type: ignore
        if reminder is not None:
            tzinfo = await reminder.get_tzinfo(interaction.user.id) # type: ignore
        return cls(argument, now=interaction.response.created_at, tzinfo=tzinfo) # type: ignore


class RelativeDelta(app_commands.Transformer, commands.Converter):
    @classmethod
    def __do_conversion(cls, argument: str) -> relativedelta:
        match = ShortTime.compiled.fullmatch(argument)
        if match is None or not match.group(0):
            raise ValueError('Invalid time provided.')

        data = {k: int(v) for k, v in match.groupdict(default=0).items()}
        return relativedelta(**data)

    async def convert(self, interaction: discord.Interaction, argument: str) -> relativedelta:
        try:
            return self.__do_conversion(argument)
        except ValueError as e:
            raise commands.BadArgument(str(e)) from None

    async def transform(self, interaction: discord.Interaction, value: str) -> relativedelta:
        try:
            return self.__do_conversion(value)
        except ValueError as e:
            raise app_commands.AppCommandError(str(e)) from None


class HumanTime:
    calendar = pdt.Calendar(version=pdt.VERSION_CONTEXT_STYLE)

    def __init__(
        self,
        argument: str,
        *,
        now: Optional[datetime.datetime] = None,
        tzinfo: datetime.tzinfo = datetime.timezone.utc,
    ):
        now = now or datetime.datetime.now(tzinfo)
        dt, status = self.calendar.parseDT(argument, sourceTime=now, tzinfo=None)
        if not status.hasDateOrTime:
            raise commands.BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days".')

        if not status.hasTime:
            # replace it with the current time
            dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        self.dt: datetime.datetime = dt.replace(tzinfo=tzinfo)
        if now.tzinfo is None:
            now = now.replace(tzinfo=datetime.timezone.utc)
        self._past: bool = self.dt < now

    @classmethod
    async def convert(cls, interaction: discord.Interaction, argument: str) -> Self:
        tzinfo = datetime.timezone.utc
        reminder = interaction.bot.reminder # type: ignore
        if reminder is not None:
            tzinfo = await reminder.get_tzinfo(interaction.user.id) # type: ignore
        return cls(argument, now=interaction.created_at, tzinfo=tzinfo) # type: ignore


class Time(HumanTime):
    def __init__(
        self,
        argument: str,
        *,
        now: Optional[datetime.datetime] = None,
        tzinfo: datetime.tzinfo = datetime.timezone.utc,
    ):
        try:
            o = ShortTime(argument, now=now, tzinfo=tzinfo)
        except Exception as e:
            super().__init__(argument, now=now, tzinfo=tzinfo)
        else:
            self.dt = o.dt
            self._past = False


class FutureTime(Time):
    def __init__(
        self,
        argument: str,
        *,
        now: Optional[datetime.datetime] = None,
        tzinfo: datetime.tzinfo = datetime.timezone.utc,
    ):
        super().__init__(argument, now=now, tzinfo=tzinfo)

        if self._past:
            raise commands.BadArgument('This time is in the past.')


class BadTimeTransform(app_commands.AppCommandError):
    pass


class TimeTransformer(app_commands.Transformer):
    async def transform(self, interaction: discord.Interaction, value: str) -> datetime.datetime:
        tzinfo = datetime.timezone.utc
        reminder = interaction.client.get_cog('Reminder')
        if reminder is not None:
            tzinfo = await reminder.get_tzinfo(interaction.user.id)

        now = interaction.created_at.astimezone(tzinfo)
        try:
            short = ShortTime(value, now=now, tzinfo=tzinfo)
        except commands.BadArgument:
            try:
                human = FutureTime(value, now=now, tzinfo=tzinfo)
            except commands.BadArgument as e:
                raise BadTimeTransform(str(e)) from None
            else:
                return human.dt
        else:
            return short.dt


class FriendlyTimeResult:
    dt: datetime.datetime
    arg: str

    __slots__ = ('dt', 'arg')

    def __init__(self, dt: datetime.datetime):
        self.dt = dt
        self.arg = ''

    async def ensure_constraints(self, interaction: discord.Interaction, uft: UserFriendlyTime, now: datetime.datetime, remaining: str) -> None:
        if self.dt < now:
            raise commands.BadArgument('This time is in the past.')

        if not remaining:
            if uft.default is None:
                raise commands.BadArgument('Missing argument after the time.')
            remaining = uft.default

        if uft.converter is not None:
            self.arg = await uft.converter.convert(interaction, remaining)
        else:
            self.arg = remaining


class UserFriendlyTime(commands.Converter):
    """That way quotes aren't absolutely necessary."""

    def __init__(
        self,
        converter: Optional[Union[type[commands.Converter], commands.Converter]] = None,
        *,
        default: Any = None,
    ):
        if isinstance(converter, type) and issubclass(converter, commands.Converter):
            converter = converter()

        if converter is not None and not isinstance(converter, commands.Converter):
            raise TypeError('commands.Converter subclass necessary.')

        self.converter: commands.Converter = converter  # type: ignore  # It doesn't understand this narrowing
        self.default: Any = default

    async def convert(self, interaction: discord.Interaction, argument: str) -> FriendlyTimeResult:
        calendar = HumanTime.calendar
        regex = ShortTime.compiled
        now = interaction.response.created_at # type: ignore

        reminder = interaction.bot.reminder # type: ignore
        tzinfo = datetime.timezone.utc
        if reminder is not None:
            tzinfo = await reminder.get_tzinfo(interaction.user.id) # type: ignore

        match = regex.match(argument)
        if match is not None and match.group(0):
            data = {k: int(v) for k, v in match.groupdict(default=0).items()}
            remaining = argument[match.end() :].strip()
            dt = now + relativedelta(**data)
            result = FriendlyTimeResult(dt.astimezone(tzinfo))
            await result.ensure_constraints(interaction, self, now, remaining)
            return result

        if match is None or not match.group(0):
            match = ShortTime.discord_fmt.match(argument)
            if match is not None:
                result = FriendlyTimeResult(
                    datetime.datetime.fromtimestamp(int(match.group('ts')), tz=datetime.timezone.utc).astimezone(tzinfo)
                )
                remaining = argument[match.end() :].strip()
                await result.ensure_constraints(interaction, self, now, remaining)
                return result

        # Apparently nlp does not like "from now".
        # It likes "from x" in other cases though so let me handle the 'now' case.
        if argument.endswith('from now'):
            argument = argument[:-8].strip()

        if argument[0:2] == 'me':
            # Starts with "me to", "me in", or "me at ".
            if argument[0:6] in ('me to ', 'me in ', 'me at '):
                argument = argument[6:]

        # Have to adjust the timezone so pdt knows how to handle things like "tomorrow at 6pm" in an aware way.
        now = now.astimezone(tzinfo)
        elements = calendar.nlp(argument, sourceTime=now)
        if elements is None or len(elements) == 0:
            raise commands.BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days".')

        # handle the following cases:
        # "date time" foo
        # date time foo
        # foo date time

        # first the first two cases:
        dt, status, begin, end, dt_string = elements[0]

        if not status.hasDateOrTime:
            raise commands.BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days".')

        if begin not in (0, 1) and end != len(argument):
            raise commands.BadArgument(
                'Time is either in an inappropriate location, which '
                'must be either at the end or beginning of your input, '
                'or I just flat out did not understand what you meant. Sorry.'
            )

        dt = dt.replace(tzinfo=tzinfo)
        if not status.hasTime:
            # Replace it with the current time.
            dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        if status.hasTime and not status.hasDate and dt < now:
            # If it's in the past, and it has a time but no date,
            # assume it's for the next occurrence of that time.
            dt = dt + datetime.timedelta(days=1)

        # If midnight is provided, just default to next day.
        if status.accuracy == pdt.pdtContext.ACU_HALFDAY:
            dt = dt + datetime.timedelta(days=1)

        result = FriendlyTimeResult(dt)
        remaining = ''

        if begin in (0, 1):
            if begin == 1:
                # Check if it's quoted:
                if argument[0] != '"':
                    raise commands.BadArgument('Expected quote before time input...')

                if not (end < len(argument) and argument[end] == '"'):
                    raise commands.BadArgument('If the time is quoted, you must unquote it.')

                remaining = argument[end + 1 :].lstrip(' ,.!')
            else:
                remaining = argument[end:].lstrip(' ,.!')
        elif len(argument) == end:
            remaining = argument[:begin].strip()

        await result.ensure_constraints(interaction, self, now, remaining)
        return result


def human_timedelta(
    dt: datetime.datetime,
    *,
    source: Optional[datetime.datetime] = None,
    accuracy: Optional[int] = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
    now = source or datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)

    # Microsecond free zone.
    now = now.replace(microsecond=0)
    dt = dt.replace(microsecond=0)

    # Make sure they're both in the timezone.
    now = now.astimezone(datetime.timezone.utc)
    dt = dt.astimezone(datetime.timezone.utc)

    # This implementation uses relativedelta instead of the much more obvious
    # divmod approach with seconds because the seconds approach is not entirely
    # accurate once you go over 1 week in terms of accuracy since you have to
    # hardcode a month as 30 or 31 days.
    # A query like "11 months" can be interpreted as "!1 months and 6 days".
    if dt > now:
        delta = relativedelta(dt, now)
        output_suffix = ''
    else:
        delta = relativedelta(now, dt)
        output_suffix = ' ago' if suffix else ''

    attrs = [
        ('year', 'y'),
        ('month', 'mo'),
        ('day', 'd'),
        ('hour', 'h'),
        ('minute', 'm'),
        ('second', 's'),
    ]

    output = []
    for attr, brief_attr in attrs:
        elem = getattr(delta, attr + 's')
        if not elem:
            continue

        if attr == 'day':
            weeks = delta.weeks
            if weeks:
                elem -= weeks * 7
                if not brief:
                    output.append(format(plural(weeks), 'week'))
                else:
                    output.append(f'{weeks}w')

        if elem <= 0:
            continue

        if brief:
            output.append(f'{elem}{brief_attr}')
        else:
            output.append(format(plural(elem), attr))

    if accuracy is not None:
        output = output[:accuracy]

    if len(output) == 0:
        return 'now'
    else:
        if not brief:
            return human_join(output, final='and') + output_suffix
        else:
            return ' '.join(output) + output_suffix

def format_relative(dt: datetime.datetime) -> str:
    return format_dt(dt, 'R')
