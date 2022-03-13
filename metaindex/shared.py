"""Functions, names, and identifiers shared in the code"""
import codecs
import datetime
from pathlib import Path

from .humanizer import humanize


EXTRA = 'extra.'
IS_RECURSIVE = 'extra_metadata_is_recursive'
LAST_MODIFIED = 'extra_metadata_last_modified'

DUBLINCORE_TAGS = {
    'contributor',
    'coverage',
    'creator',
    'date',
    'description',
    'format',
    'identifier',
    'language',
    'publisher',
    'relation',
    'rights',
    'source',
    'subject',
    'title',
    'type',
}


class MetadataValue:
    """A metadata value"""
    def __init__(self, value, humanized=None):
        self.raw_value = value
        self.humanized_value = humanized

    def humanized(self):
        """The humanized version of the value"""
        return self.humanized_value or str(self.raw_value)

    def __eq__(self, other):
        if isinstance(other, MetadataValue):
            return self.raw_value == other.raw_value and \
                   self.humanized_value == other.humanized_value
        if isinstance(other, str):
            return self.humanized() == other
        if isinstance(other, type(self.raw_value)):
            return self.raw_value == other
        return False

    def __format__(self, _):
        return self.humanized()

    def __str__(self):
        return self.humanized()

    def __repr__(self):
        return f'{type(self).__name__}("{self.raw_value}", "{self.humanized_value}")'

    def __lt__(self, other):
        return self.humanized() < other.humanized()

    def __hash__(self):
        return hash(self.humanized())


class CacheEntry:
    """A cached metadata entry for an item in the filesystem"""

    AUTO_KEYS = {'filename', 'last_modified'}
    FILENAME = 'filename'
    LAST_MODIFIED = 'last_modified'

    def __init__(self, path, metadata=None, last_modified=None):
        self.path = Path(path) if isinstance(path, str) else path
        """The path to the file object in the filesystem.
        Does not need to exist."""

        self.metadata = metadata or {}
        """The dictionary of lower-case keys,
        mapping to a list of ``MetadataValue``."""

        if isinstance(metadata, (list, set)):
            self.metadata = {}
            for key, value in metadata:
                if key not in self.metadata:
                    self.metadata[key] = []
                self.add(key, value)
        elif isinstance(metadata, dict):
            self.metadata = {}
            for key, values in metadata.items():
                if not isinstance(values, (list, tuple, set)):
                    values = [values]
                for value in values:
                    self.add(key, value)
        elif metadata is not None:
            raise TypeError()

        self.last_modified = last_modified or datetime.datetime.min
        """The time stamp of when the file was modified most recently"""

    def __lt__(self, other):
        return str(self.path) < str(other.path)

    def __len__(self):
        """The number of metadata key/value pairs"""
        return sum(len(values) for values in self.metadata.values())

    def __iter__(self):
        """Iterate through all metadata key/value pairs"""
        for key, values in self.metadata.items():
            for value in values:
                yield key, value
        if self.path is not None:
            yield (type(self).FILENAME, self.path.name)
        yield (type(self).LAST_MODIFIED, self.last_modified)

    def __contains__(self, key):
        """Check whether key is in the metadata"""
        key = str(key).lower()
        return key in self.metadata or \
               key in type(self).AUTO_KEYS

    def __repr__(self):
        return f"<{type(self).__name__} path={self.path}>"

    def __getitem__(self, key):
        """Get the list of ``MetadataValue`` of ``key``

        :param key: The key to look for
        :return: A list of ``MetadataValue``s, may be empty.
        """
        return self.get(key)

    def get(self, key):
        """Get the list of ``MetadataValue`` of ``key``

        :param key: The key to look for
        :return: A list of ``MetadataValue``, may be empty.
        """
        if key == type(self).FILENAME and self.path is not None:
            return [self.path.name]
        if key == type(self).LAST_MODIFIED:
            return [self.last_modified]
        return self.metadata.get(key.lower(), [])

    def ensure_last_modified(self, force=False):
        """Ensure that the ``last_modified`` value is set.

        If it is not set, the last modified datetime will be
        obtained by querying the filesystem, which may be slow and
        fail.

        This function call will not fail though: in case of exceptions
        on the filesystem level the ``last_modified`` date will simply be
        set to ``datetime.datetime.min``.

        :param force: Whether or not to enforce an update even if the
                      entry has a valid value.
        :return: Updated ``last_modified`` value.
        """
        if force or self.last_modified in [None, datetime.datetime.min]:
            if self.last_modified is None:
                self.last_modified = datetime.datetime.min
            try:
                self.last_modified = get_last_modified(self.path)
            except (OSError, ValueError):
                pass  # keep the old value
        return self.last_modified

    def keys(self):
        """Return all metadata keys"""
        return list(set(self.metadata.keys()) | type(self).AUTO_KEYS)

    def add(self, key, value):
        """Add metadata ``key:value`` to this entry

        This does not update the underlying persistence layer.

        You can set the ``last_modified`` property through this, too. But there
        will always only be one value and it can only be changed forward in time.
        If you need to set the value of ``last_modified`` to something that's
        earlier than the current value, just set the property directly instead
        of calling ``.add``.
        """
        key = key.lower()

        if key == type(self).LAST_MODIFIED:
            if not isinstance(value, datetime.datetime):
                return
            if self.last_modified == datetime.datetime.min:
                self.last_modified = value
            elif value == datetime.datetime.min:
                pass
            elif value > self.last_modified:
                self.last_modified = value

        if key in type(self).AUTO_KEYS:
            return

        if not isinstance(value, MetadataValue):
            value = MetadataValue(value)

        if value.humanized_value is None:
            value.humanized_value = humanize(key, value.raw_value)

        if key not in self.metadata:
            self.metadata[key] = []
        self.metadata[key].append(value)

    def update(self, other, accept_duplicates=False):
        """Add metadata from ``other`` into this entry

        Will not add duplicate ``key:value`` pairs unless ``accept_duplicates``
        is set to ``True``.

        This call will also update the ``last_modified`` property to be the
        most recent of both ``self`` and ``other``.
        """
        for key, value in other:
            if key in type(self).AUTO_KEYS:
                continue
            if not accept_duplicates and value in self[key]:
                continue
            self.add(key, value)
        self.add(type(self).LAST_MODIFIED, other.last_modified)

    def pop(self, key):
        """Remove all entries of ``key`` from the metadata and return them

        After the operation ``self[key]`` will return only an empty list.
        """
        return self.metadata.pop(key, [])

    def __delitem__(self, keyvalue):
        """Delete the metadata key/value or key

        :param keyvalue: key of the metadata values to delete or key/value
                         pair to delete
        :type keyvalue: ``str`` (the key) or a tuple/list of ``(key, value)``
        """
        self.delete(keyvalue)

    def delete(self, keyvalue):
        """Delete the metadata key/value or key

        :param keyvalue: key of the metadata values to delete or key/value
                         pair to delete
        :type keyvalue: ``str`` (the key) or a tuple/list of ``(key, value)``
        """
        if isinstance(keyvalue, (list, tuple)):
            key, value = keyvalue
        else:
            key = keyvalue
            value = None
        key = key.lower()

        if key not in self.metadata:
            return

        if value is not None:
            to_delete = [v
                         for v in self.metadata[key]
                         if v == value]
            for item in to_delete:
                self.metadata[key].remove(item)

        if len(self.metadata[key]) == 0 or value is None:
            del self.metadata[key]


def get_last_modified(file_):
    """Return the last_modified datetime of the given file.

    This will drop the microsecond part of the timestamp! The reasoning is that
    last_modified will be taken during database cache updates. If a change
    happens at the same second to a file, just after the indexer passed it,
    there's probably a good chance the file gets modified again in the near
    future at which point the indexer will pick up the change.
    Other than that, the cache can forcefully be cleared, too.
    """
    return datetime.datetime.fromtimestamp(file_.stat().st_mtime).replace(microsecond=0)


def get_all_fulltext(metadata):
    """Extract all fulltext values from the metadata"""
    fulltext = ''
    for key in {k for k in metadata.keys() if k.lower().endswith('.fulltext')}:
        fulltext += "".join(metadata[key])
    return fulltext


def to_utf8(raw):
    if isinstance(raw, str):
        return raw
    encoding = None
    skip = 1

    if raw.startswith(codecs.BOM_UTF8):
        encoding = 'utf-8'
    elif raw.startswith(codecs.BOM_UTF16_BE):
        encoding = 'utf-16-be'
    elif raw.startswith(codecs.BOM_UTF16_LE):
        encoding = 'utf-16-le'
    elif raw.startswith(codecs.BOM_UTF32_BE):
        encoding = 'utf-32-be'
    elif raw.startswith(codecs.BOM_UTF32_LE):
        encoding = 'utf-32-le'
    else:
        # just best efford
        encoding = 'utf-8'
        skip = 0

    try:
        text = str(raw, encoding=encoding).strip()
        return text[skip:]  # drop the BOM, if applicable
    except UnicodeError:
        pass
    return None
