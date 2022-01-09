"""General access to all methods of metadata storage"""
import pathlib

from multidict import MultiDict

from metaindex import json
from metaindex import opf
from metaindex.shared import IS_RECURSIVE

try:
    from metaindex import yaml
except ImportError:
    yaml = None


STORES = [json, opf]
BY_SUFFIX = dict([(store.SUFFIX, store) for store in STORES])

if yaml is not None:
    STORES.append(yaml)
    BY_SUFFIX[yaml.SUFFIX] = yaml


def get(metadatafile, prefix='extra.'):
    """Parse this metadata file for a single file.

    metadatafile can be a pathlib.Path, str, or a byte stream.

    Returns a multidict of the extra tags from this file.
    Every tag name is prefixed with 'prefix'

    These extra keys will be added:
    - extra_metadata_is_recursive: True if this set of tags has to be applied to
                                   all files in all subfolders,
    - extra_metadata_last_modified: datetime of when the metadatafile was modified
    """
    metadatafile = pathlib.Path(metadatafile)

    if metadatafile.suffix not in BY_SUFFIX:
        return {}

    return BY_SUFFIX[metadatafile.suffix].get(metadatafile, prefix)


def get_for_collection(metadatafile, prefix='extra.', basepath=None):
    """Parse this metadata file for a collection of files.

    metadatafile can be a pathlib.Path or a byte stream.
    If you provide a byte stream, you must provide basepath as the parent path
    for the context of the collection.

    Returns a mapping filename -> multidict of the extra tags from this file.
    The filename key may be a directory, thus affecting all files in the directory.
    Every tag name is prefixed with 'prefix'.

    Per file these extra keys will be added:
    - extra_metadata_is_recursive: True if this set of tags has to be applied to
                                   all files in all subfolders,
    - extra_metadata_last_modified: datetime of when the metadatafile was modified
    """
    metadatafile = pathlib.Path(metadatafile)

    if metadatafile.suffix not in BY_SUFFIX:
        return {}

    return BY_SUFFIX[metadatafile.suffix].get_for_collection(metadatafile, prefix, basepath)


def sidecars_for(filepath):
    """Returns the possible metafilenames for this file.
    The files may not exist."""
    return [filepath.parent / (filepath.stem + store.SUFFIX) for store in STORES]


def store(metadata, filename, suffix=None):
    """Store this metadata information in that metadata file

    As filename you may provide a filename or a byte stream for writing the data.
    If you provide a byte stream, you must provide suffix, otherwise the correct
    store cannot be resolved.

    Metadata may be a list in which case filename is going to be a collection
    metadata file.
    Or metadata may be a multidict in which case filename is considered a
    sidecar file.
    """
    if suffix is None:
        suffix = pathlib.Path(filename).suffix
    return BY_SUFFIX[suffix].store(metadata, filename)


def as_collection(metadata, strip_prefix='extra.'):
    """Return a store-compatible collection style dict of metadata (coming from get_for_collection)

    Expects a dict as returned by ``get_for_collection``, and will convert it
    to the correct form as expected by ``store``.
    That means it will convert the keys from pathlib.Path to str, remove
    IS_RECURSIVE tags and, if ``strip_prefix`` is set, it will remove the
    given prefix.

    So, technically you could run ``store(as_collection(get_for_collection(sidecar)), sidecar)``
    and it would result in the identical sidecar file.
    """
    converted = {}
    for filename, entry in metadata.items():
        if isinstance(filename, pathlib.Path):
            key = filename.name
        else:
            key = str(filename)

        if filename.is_dir():
            key = '**' if any(k == IS_RECURSIVE and v for k, v in entry.items()) \
                  else '*'

        converted[key] = MultiDict([(k[len(strip_prefix):]
                                       if strip_prefix is not None else k,
                                     v)
                                     for k, v in entry.items()
                                     if k != IS_RECURSIVE])

    return converted
