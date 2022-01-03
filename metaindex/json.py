import json
import pathlib

import multidict

from metaindex import logger
from metaindex import shared


SUFFIX = '.json'


def get(filename, prefix):
    if isinstance(filename, (str, pathlib.Path)):
        logger.debug(f"Reading JSON metadata from {filename}")
        with open(filename, "rt", encoding="utf-8") as fh:
            return get(fh, prefix)

    success, data = _read_json_file(filename)

    if not success:
        return {}

    result = multidict.MultiDict()

    for key in data.keys():
        values = data[key]

        if not isinstance(values, list):
            values = [values]
        
        for value in values:
            result.add(prefix + key, value)

    result.add(shared.IS_RECURSIVE, False)

    return result


def get_for_collection(filename, prefix, basepath=None):
    if isinstance(filename, pathlib.Path):
        logger.debug(f"Reading collection JSON metadata from {filename}")
        with open(filename, "rt", encoding="utf-8") as fh:
            return get_for_collection(fh, prefix, filename.parent)

    success, data = _read_json_file(filename)

    if not success:
        return {}

    if not any([isinstance(value, dict) for value in data.values()]):
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
            result[fulltargetname] = multidict.MultiDict()

        for key in data[targetfile].keys():
            values = data[targetfile][key]

            if not isinstance(values, list):
                values = [values]
            
            for value in values:
                result[fulltargetname].add(prefix + key, value)

        result[fulltargetname].add(shared.IS_RECURSIVE, targetfile == '**')

    return result


def store(metadata, filename):
    """Store this metadata information in that metadata file"""
    if isinstance(filename, (str, pathlib.Path)):
        with open(filename, 'wt', encoding='utf-8') as fh:
            return store(metadata, fh)

    if not isinstance(metadata, (multidict.MultiDict, dict)):
        raise TypeError(f"Expected MultiDict or dict, got {type(metadata)}")

    blob = json.dumps(shared.multidict_to_dict(metadata), indent=2, ensure_ascii=False, sort_keys=True)
    filename.write(blob)


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

