import inspect
from typing import Any

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
        to_remove: str | None = None
        flag_converter: type[commands.FlagConverter] | None = None
        for key, param in command.clean_params.items():
            if inspect.isclass(param.converter) and issubclass(
                param.converter, commands.FlagConverter
            ):
                if to_remove:
                    raise RuntimeError("This formatter only supports one FlagConverter")
                to_remove = key
                flag_converter = param.converter

        if to_remove:
            command.params.pop(to_remove)
        super().add_command_arguments(command)
        if not flag_converter:
            return

        if command.clean_params:
            self.paginator.add_line()
        self.paginator.add_line("Flags:")

        prefix = flag_converter.__commands_flag_prefix__
        for flag in flag_converter.get_flags().values():
            joiner = " " if prefix else "|"
            names = joiner.join(f"{prefix}{x}" for x in (flag.name, *flag.aliases))
            if flag.required:
                entry = f"{(self.indent - 1) * " "}*{names}"
            else:
                entry = f"{self.indent * " "}{names}"
            if flag.default:
                entry += f" = {flag.default}"
            entry = self.shorten_text(entry)
            if flag.description:
                entry += self.shorten_text(f"\n{self.indent * 2 * " "}{flag.description}")

            self.paginator.add_line(entry)
