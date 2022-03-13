import json
import pathlib

from metaindex import logger
from metaindex import shared


SUFFIX = '.json'


def get(filename):
    if isinstance(filename, (str, pathlib.Path)):
        logger.debug(f"Reading JSON metadata from {filename}")
        with open(filename, "rt", encoding="utf-8") as fh:
            return get(fh)

    entry = shared.CacheEntry(None)
    if hasattr(filename, 'name'):
        entry.path = pathlib.Path(filename.name)

    success, data = _read_json_file(filename)

    if not success:
        return entry

    for key in data.keys():
        values = data[key]

        if not isinstance(values, list):
            values = [values]

        for value in values:
            entry.add(shared.EXTRA + key, value)

    entry.add(shared.IS_RECURSIVE, False)

    return entry


def get_for_collection(filename, basepath=None):
    if isinstance(filename, (pathlib.Path, str)):
        logger.debug(f"Reading collection JSON metadata from {filename}")
        with open(filename, "rt", encoding="utf-8") as fh:
            return get_for_collection(fh, pathlib.Path(filename).parent)

    success, data = _read_json_file(filename)

    if not success:
        return {}

    if not any(isinstance(value, dict) for value in data.values()):
        # the file itself is a dictionary of values and lists, so probably
        # this means that the metadata here applies to all metadat in the directory
        logger.debug(f"Assuming flat json file means it's for all files in {basepath}")
        data = {'*': data}

    result = {}

    for targetfile in data.keys():
        if not isinstance(data[targetfile], dict):
            logger.warning(f"Key {targetfile} in {filename} is not a dictionary. Skipping.")
            continue

        if targetfile in ['*', '**']:
            fulltargetname = basepath
        else:
            fulltargetname = basepath / targetfile

        if fulltargetname not in result:
            result[fulltargetname] = shared.CacheEntry(pathlib.Path(fulltargetname))

        for key in data[targetfile].keys():
            values = data[targetfile][key]

            if not isinstance(values, list):
                values = [values]

            for value in values:
                result[fulltargetname].add(shared.EXTRA + key, value)

        result[fulltargetname].add(shared.IS_RECURSIVE, targetfile == '**')

    return result


def store(metadata, filename):
    """Store this metadata information in that metadata file"""
    if isinstance(filename, (str, pathlib.Path)):
        with open(filename, 'wt', encoding='utf-8') as fh:
            return store(metadata, fh)

    if isinstance(metadata, shared.CacheEntry):
        data = _cacheentry_as_dict(metadata)
    elif isinstance(metadata, list) and \
         all(isinstance(e, shared.CacheEntry) for e in metadata):
        data = {}
        for item in sorted(metadata):
            if item.path.is_dir():
                key = '*'
                if item[shared.IS_RECURSIVE] == [True]:
                    key = '**'
            else:
                key = item.path.name
            data[key] = _cacheentry_as_dict(item)
    else:
        raise TypeError()

    blob = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    filename.write(blob)


def _cacheentry_as_dict(entry):
    return {key.split('.', 1)[1]: [v.raw_value for v in values]
            for key, values in entry.metadata.items()
            if key.startswith(shared.EXTRA)}


def _read_json_file(filename):
    try:
        data = json.loads(filename.read())
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to read metadata from {filename}: {exc}")
        return False, {}

    if not isinstance(data, dict):
        logger.error(f"JSON metadata file {filename} does not contain a dictionary")
        return False, {}

    return True, data
