# SPDX-License-Identifier: GPL-3.0-only

"""Helpers for synchronizing common scrcpy options with an argument list."""

from __future__ import annotations

from collections.abc import Callable, Sequence


def get_value(args: Sequence[str], option: str) -> str:
    """Return the first value in equals or split form, or an empty string.

    A split option only consumes a following token when it is not option-looking;
    this keeps a missing value from swallowing an unrelated option.
    """
    prefix = f"{option}="
    for index, arg in enumerate(args):
        if arg.startswith(prefix):
            return arg[len(prefix):]
        if arg == option and index + 1 < len(args) and not _looks_like_option(args[index + 1]):
            return args[index + 1]
    return ""


def set_value(args: Sequence[str], option: str, value: str) -> list[str]:
    """Set one value option in canonical form, removing all existing forms.

    Split options consume their following token only when it is not
    option-looking. A missing split value therefore removes only the option.
    """
    prefix = f"{option}="
    normalized = value.strip()
    replacement = f"{prefix}{normalized}" if normalized else None
    result: list[str] = []
    inserted = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg.startswith(prefix):
            if replacement is not None and not inserted:
                result.append(replacement)
                inserted = True
            index += 1
            continue
        if arg == option:
            if replacement is not None and not inserted:
                result.append(replacement)
                inserted = True
            index += 1
            if index < len(args) and not _looks_like_option(args[index]):
                index += 1
            continue
        result.append(arg)
        index += 1
    if replacement is not None and not inserted:
        result.append(replacement)
    return result


def _looks_like_option(arg: str) -> bool:
    return arg.startswith("-")


def has_flag(args: Sequence[str], flag: str, *, allow_value: bool = False) -> bool:
    """Return whether a flag is present, optionally accepting ``--flag=value``."""
    return any(_matches_flag(arg, flag, allow_value) for arg in args)


def set_flag(
    args: Sequence[str],
    flag: str,
    enabled: bool,
    *,
    allow_value: bool = False,
) -> list[str]:
    """Enable or disable one flag while preserving unrelated arguments."""
    predicate = lambda arg: _matches_flag(arg, flag, allow_value)
    if not enabled:
        return [arg for arg in args if not predicate(arg)]

    existing = next((arg for arg in args if predicate(arg)), None)
    return _replace_matching(args, predicate, existing or flag)


def _matches_flag(arg: str, flag: str, allow_value: bool) -> bool:
    return arg == flag or (allow_value and arg.startswith(f"{flag}="))


def _replace_matching(
    args: Sequence[str],
    predicate: Callable[[str], bool],
    replacement: str | None,
) -> list[str]:
    result: list[str] = []
    inserted = False
    for arg in args:
        if predicate(arg):
            if replacement is not None and not inserted:
                result.append(replacement)
                inserted = True
            continue
        result.append(arg)
    if replacement is not None and not inserted:
        result.append(replacement)
    return result
