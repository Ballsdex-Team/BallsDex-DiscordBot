import inspect
from typing import Any

import discord
from discord.ext import commands


class HelpCommand(commands.DefaultHelpCommand):
    """
    An override of the default help command to show flag converters in text commands.
    """

    def get_command_signature(self, command: commands.Command[Any, ..., Any]) -> str:
        if not self.show_parameter_descriptions:
            return super().get_command_signature(command)

        name = command.qualified_name
        if len(command.aliases) > 0:
            aliases = "|".join(command.aliases)
            name += f"|{aliases}"

        base = f"{self.context.clean_prefix}{name}"

        for param in command.clean_params.values():
            if inspect.isclass(param.converter) and issubclass(param.converter, commands.FlagConverter):
                continue
            param_str = param.displayed_name or param.name
            if param.displayed_default:
                param_str += f"={param.displayed_default}"
            if param.required:
                param_str = f"<{param_str}>"
            else:
                param_str = f"[{param_str}]"
            base += f" {param_str}"
        return base

    def add_command_arguments(self, command: commands.Command[Any, ..., Any]) -> None:
        arguments = command.clean_params.values()
        if not arguments:
            return

        flag_converter: type[commands.FlagConverter] | None = None
        for param in arguments:
            if inspect.isclass(param.converter) and issubclass(param.converter, commands.FlagConverter):
                if flag_converter:
                    raise RuntimeError("This formatter only supports one FlagConverter")
                flag_converter = param.converter

        if len(arguments) > 1 or flag_converter is None:
            self.paginator.add_line(self.arguments_heading)
            max_size = self.get_max_size(arguments)  # type: ignore # not a command

            get_width = discord.utils._string_width
            for argument in arguments:
                if argument.converter == flag_converter:
                    continue
                name = argument.displayed_name or argument.name
                width = max_size - (get_width(name) - len(name))
                description = argument.description or self.default_argument_description
                entry = f"{self.indent * ' '}{name:<{width}} {description}"
                # we do not want to shorten the default value, if any.
                entry = self.shorten_text(entry)
                if argument.displayed_default is not None:
                    entry += f" (default: {argument.displayed_default})"

                self.paginator.add_line(entry)

        if not flag_converter:
            return

        if len(arguments) > 1:
            self.paginator.add_line()
        self.paginator.add_line("Flags:")

        required_once = False
        prefix = flag_converter.__commands_flag_prefix__
        for flag in flag_converter.get_flags().values():
            joiner = " " if prefix else "|"
            names = joiner.join(f"{prefix}{x}" for x in (flag.name, *flag.aliases))
            if flag.required:
                required_once = True
                entry = f"{(self.indent - 1) * ' '}*{names}"
            else:
                entry = f"{self.indent * ' '}{names}"
            if flag.default:
                entry += f"={flag.default}"
            entry = self.shorten_text(entry)
            if flag.description:
                entry += self.shorten_text(f"\n{self.indent * 2 * ' '}{flag.description}")

            self.paginator.add_line(entry)

        if required_once:
            self.paginator.add_line("*required")
