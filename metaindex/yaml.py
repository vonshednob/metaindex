import pathlib

import yaml

from metaindex import shared
from metaindex import logger


SUFFIX = '.yaml'


def get(filename):
    if isinstance(filename, (pathlib.Path, str)):
        logger.debug(f"Reading YAML metadata from {filename}")
        with open(filename, "rt", encoding="utf-8") as fh:
            return get(fh)

    result = shared.CacheEntry(None)
    if hasattr(filename, 'name'):
        result.path = pathlib.Path(filename.name)

    success, data = _read_yaml_file(filename)

    if not success:
        return result

    for key in data.keys():
        values = data[key]

        if not isinstance(values, list):
            values = [values]

        for value in values:
            result.add(shared.EXTRA + key, value)

    result.add(shared.IS_RECURSIVE, False)

    return result


def get_for_collection(filename, basepath=None):
    if isinstance(filename, (pathlib.Path, str)):
        logger.debug(f"Reading collection YAML metadata from {filename}")
        with open(filename, "rt", encoding="utf-8") as fh:
            return get_for_collection(fh, pathlib.Path(filename).parent)

    assert basepath is not None
    result = {}

    success, data = _read_yaml_file(filename)

    if not success:
        return result

    if not any(isinstance(value, dict) for value in data.values()):
        # the file itself is a dictionary of values and lists, so probably
        # this means that the metadata here applies to all metadat in the directory
        logger.debug(f"Assuming flat yaml file means it's for all files in {basepath}")
        data = {'*': data}

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

    blob = yaml.safe_dump(data, indent=4, allow_unicode=True)
    filename.write(blob)


def _cacheentry_as_dict(entry):
    return {key.split('.', 1)[1]: [v.raw_value for v in values]
            for key, values in entry.metadata.items()
            if key.startswith(shared.EXTRA)}


def _read_yaml_file(filename):
    try:
        data = yaml.safe_load(filename.read())
    except Exception as exc:
        logger.error("Could not read YAML sidecar file: %s", exc)
        return False, {}

    if not isinstance(data, dict):
        logger.error(f"YAML metadata file {filename} does not contain a dictionary")
        return False, {}

    return True, data
