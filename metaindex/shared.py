"""Functions, names, and identifiers shared in the code"""
import codecs
import datetime

import multidict


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


def multidict_to_dict(source):
    """Convert a multidict to a dict with either lists of entries or a single entry
    """
    if not isinstance(source, (multidict.MultiDict, dict)):
        return source

    result = dict()
    for key in {k for k in source.keys()}:
        if isinstance(source, multidict.MultiDict):
            values = [multidict_to_dict(v) if isinstance(v, multidict.MultiDict) else v for v in source.getall(key)]
        else:
            values = [multidict_to_dict(source[key]) if isinstance(source[key], multidict.MultiDict) else source[key]]

        if len(values) == 1:
            result[key] = values[0]
        else:
            result[key] = values
    return result


def get_all_fulltext(metadata):
    """Extract all fulltext values from the metadata"""
    fulltext = ''
    for key in {k for k in metadata.keys() if k.lower().endswith('.fulltext')}:
        fulltext += "".join(metadata.getall(key))
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
