"""Formatters to make metadata tags' values human-readable

Formatters are called 'humanizers', as they are meant to make human-readble
strings from values.
"""
import datetime
from enum import IntEnum


_formatter_by_tag = {}


def humanize(tag, value):
    """Make the metadata value human-readable

    :param tag: The key of the metadata value
    :param value: The actual raw value
    :return: Returns ``None`` or a human-readable version ``str``
    :rtype: ``str`` or ``None``
    """
    for formatter in find_humanizers(tag):
        human_readable = formatter(value)
        if human_readable is not None:
            return human_readable


def find_humanizers(tag):
    """Return a list of humanizers for this tag"""
    tag = tag.lower()
    name = tag

    if '.' in tag:
        _, name = tag.split('.', 1)

    humanizers = _formatter_by_tag.get(tag, [])
    if '.' in tag:
        humanizers += _formatter_by_tag.get('*.' + name, [])
    humanizers += _formatter_by_tag.get('*', [])

    return [h.formatter for h in sorted(humanizers)]


class Priority(IntEnum):
    """Priority of humanizers"""
    HIGHEST = 10
    """Highest priority, humanizers with this priority will be run first"""
    HIGH = 20
    """High priority"""
    NORMAL = 50
    """Normal priority. This is the default for custom humanizers"""
    LOW = 80
    """Low priority"""
    LOWEST = 90
    """Lowest priority, humanizers with this priority will be run last"""


def register_humanizer(tags, priority=Priority.NORMAL):
    """Decorator to register a function as a humanizer

    ``tags`` can be a single tags, or a set of tags to which
    this humanizer should be applied.

    A tag may be the exact tag, like 'general.size', or ignoring
    the prefix with '*.size'.
    You may also set the tag to be '*', in case you want to translate
    rather by type; consider setting the priority to LOW in that case
    though.

    ``priority`` specifies how early in the process this humanizer
    should be called.

    The humanize function must accept a value and return either the
    human-readable version in form of a string or None, if the value
    can not be translated.
    """
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, (set, list, tuple)):
        raise TypeError("Expected a list/set/tuple of tags")

    def decorator(fnc):
        global _formatter_by_tag
        formatter = Formatter(priority, fnc)

        for tag in tags:
            tag = tag.lower()
            if tag not in _formatter_by_tag:
                _formatter_by_tag[tag] = []
            _formatter_by_tag[tag].append(formatter)
            _formatter_by_tag[tag].sort()

        return fnc

    return decorator


class Formatter:
    def __init__(self, priority, fnc):
        self.priority = priority
        self.formatter = fnc

    def __lt__(self, other):
        return self.priority < other.priority


@register_humanizer('*', Priority.LOWEST)
def format_datetime(value):
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    return None


@register_humanizer('*', Priority.LOWEST)
def format_simple(value):
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    if all(isinstance(v, (int, float, bool)) for v in sorted(value)):
        return ", ".join(str(v) for v in value)
    return None


@register_humanizer('audio.length', Priority.LOW)
def format_duration(value):
    try:
        number = float(value)
    except ValueError:
        return None

    minutes = int(number // 60)
    seconds = int(number - minutes*60)
    hours = minutes // 60
    minutes = minutes - hours*60

    value = f"{minutes:>02}:{seconds:>02}"
    if hours > 0:
        value = f"{hours}:" + value
    return value
