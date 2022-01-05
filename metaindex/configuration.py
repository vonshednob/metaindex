import configparser
import pathlib
import os
import sys
import importlib
import mimetypes

from metaindex import logger
from metaindex import stores


HERE = pathlib.Path(__file__).parent

HOME = pathlib.Path().home()
PROGRAMNAME = 'metaindex'
CONFFILENAME = PROGRAMNAME + os.path.extsep + 'conf'
CONFIGFILE = HOME / ".config" / CONFFILENAME
CACHEPATH = HOME / ".cache" / PROGRAMNAME
DATAPATH = HOME / ".local" / "share" / PROGRAMNAME

IGNORE_DIRS = [".git",
               "System Volume Information",
               ".stfolder",
               "__MACOSX"]
IGNORE_FILES = ['*.aux', '*.toc', '*.out', '*.log', '*.nav',
                '*.exe', '*.sys',
                '*.bat', '*.ps',
                '*.sh', '*.fish',
                '*~', '*.swp', '.bak', '*.sav', '*.backup']
SYNONYMS = {'author': ", ".join([
                "extra.author",
                "extra.artist",
                "extra.creator",
                "id3.artist",
                "pdf.Author",
                "rules.author",
                "Exif.Image.Artist",
                "Xmp.dc.name"]),
            'type': ", ".join([
                "extra.type",
                "rules.type",
                "Xmp.dc.type"]),
            'date': ", ".join([
                "extra.date",
                "rules.date",
                ]),
            'title': ", ".join([
                "extra.title",
                "opf.title",
                "id3.title",
                "rules.title",
                "pdf.Title",
                "Xmp.dc.title"]),
            'tags': ", ".join([
                "extra.tags",
                "pdf.Keywords",
                "pdf.Categories",
                "Xmp.dc.subject",
                "extra.subject",
                "rules.tags",
                "rules.subject",
                "pdf.Subject",
                "opf.subject"]),
            'language': ", ".join([
                "opf.language",
                "pdf.Language",
                "Xmp.dc.language",
                "extra.language",
                "rules.language",
                "ocr.language"]),
            'series': 'extra.series',
            'series_index': 'extra.series_index'}


try:
    from xdg import BaseDirectory
    CONFIGFILE = pathlib.Path(BaseDirectory.load_first_config(CONFFILENAME) or CONFIGFILE)
    CACHEPATH = pathlib.Path(BaseDirectory.save_cache_path(PROGRAMNAME) or CACHEPATH)
    DATAPATH = pathlib.Path(BaseDirectory.save_data_path(PROGRAMNAME) or DATAPATH)
except ImportError:
    BaseDirectory = None


ADDONSPATH = DATAPATH / "addons"

SECTION_GENERAL = 'General'
SECTION_SYNONYMS = 'Synonyms'
SECTION_INCLUDE = 'Include'
CONFIG_CACHE = 'cache'
CONFIG_RECURSIVE_EXTRA_METADATA = 'recursive-extra-metadata'
CONFIG_COLLECTION_METADATA = 'collection-metadata'
CONFIG_IGNORE_DIRS = 'ignore-directories'
CONFIG_IGNORE_FILES = 'ignore-files'
CONFIG_ACCEPT_FILES = 'accept-files'
CONFIG_INDEX_UNKNOWN = 'index-unknown'
CONFIG_IGNORE_INDEXERS = 'ignore-indexers'
CONFIG_IGNORE_TAGS = 'ignore-tags'
CONFIG_PREFERRED_SIDECAR_FORMAT = 'preferred-sidecar-format'
CONFIG_OCR = 'ocr'
CONFIG_MIMETYPES = 'mimetypes'

CONF_DEFAULTS = {SECTION_GENERAL: {
                    CONFIG_CACHE: str(CACHEPATH),
                    CONFIG_RECURSIVE_EXTRA_METADATA: "yes",
                    CONFIG_COLLECTION_METADATA: ".metadata, metadata",
                    CONFIG_IGNORE_DIRS: "\n".join(IGNORE_DIRS),
                    CONFIG_IGNORE_FILES: "\n".join(IGNORE_FILES),
                    CONFIG_ACCEPT_FILES: '',
                    CONFIG_INDEX_UNKNOWN: 'yes',
                    CONFIG_IGNORE_INDEXERS: '',
                    CONFIG_IGNORE_TAGS: "Exif.Image.StripByteCounts, Exif.Image.StripOffsets",
                    CONFIG_PREFERRED_SIDECAR_FORMAT: '.json, .opf',
                    CONFIG_OCR: 'no',
                 },
                 SECTION_SYNONYMS: SYNONYMS,
                 SECTION_INCLUDE: {
                 },
                }


class BaseConfiguration:
    """Convenience wrapper for configparser"""
    TRUE = ['y', 'yes', '1', 'true', 'on']
    FALSE = ['n', 'no', '0', 'false', 'off']

    def __init__(self, conf=None):
        self.conf = conf or configparser.ConfigParser(interpolation=None)
        self._userfile = None
        self._synonyms = None

    def __getitem__(self, group):
        return self.conf[group]

    def __contains__(self, item):
        return item in self.conf

    def set(self, group, key, value):
        if group not in self.conf:
            self.conf[group] = {}
        self.conf[group][key] = value

    def get(self, group, item, default=None):
        if group in self.conf:
            return self.conf[group].get(item, default)
        return default

    def bool(self, group, item, default='n'):
        return self.get(group, item, default).lower() in self.TRUE

    def number(self, group, item, default='0'):
        value = self.get(group, item, default)
        if value.isnumeric():
            return int(value)
        return None

    def path(self, group, item, default=None):
        value = self.get(group, item, default)
        if value is not None:
            value = pathlib.Path(value).expanduser().resolve()
        return value

    def list(self, group, item, default='', separator=',', strip=True, skipempty=True):
        result = []
        for v in self.get(group, item, default).split(separator):
            if strip:
                v = v.strip()
            if skipempty and len(v) == 0:
                continue
            result.append(v)
        return result


class Configuration(BaseConfiguration):
    """Wrapper for BaseConfiguration (aka configparser) with additional convenience accessors"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._collection_metadata = None

    @property
    def collection_metadata(self):
        """Return a list of all valid filenames for collection metadata.

        The list is ordered by user's preference for sidecar file format and
        name of collection metadata file.
        """
        if self._collection_metadata is None:
            lst = self.list(SECTION_GENERAL, CONFIG_COLLECTION_METADATA, None)
            if lst is not None:
                lst = sum([[fn + store.SUFFIX for store in self.get_preferred_sidecar_stores()]
                           for fn in lst], start=[])
            self._collection_metadata = lst
        return self._collection_metadata

    @property
    def synonyms(self):
        """Returns a dict of all synonyms and the attributes that they stand for

        E.g. might contain the entry 'title', mapping to ['opf.title', 'id3.title']
        """
        if self._synonyms is None:
            self._synonyms = {name: self.list(SECTION_SYNONYMS, name)
                              for name in self[SECTION_SYNONYMS]}
        return self._synonyms

    def is_sidecar_file(self, path):
        """Return True if the file at path is a sidecar file (either collection metadata or not)"""
        if not path.is_file():
            # not file? can't be a metadata file
            return False
        if path.name in self.collection_metadata:
            # the filename *is* the name of a valid collection metadata file
            return True
        # check whether there are any sidecar files for any of the valid stores
        return any(path.suffix == store.SUFFIX and
                    any(fn.is_file() and fn != path and fn.stem == path.stem
                        for fn in path.parent.iterdir())
                   for store in stores.STORES)

    def get_preferred_sidecar_stores(self):
        """Returns a list of all available metadata stores, sorted by preference of the user"""
        preferred = self.list(SECTION_GENERAL, CONFIG_PREFERRED_SIDECAR_FORMAT, '.json')
        preferred = [stores.BY_SUFFIX[suffix] for suffix in preferred if suffix in stores.BY_SUFFIX]
        return preferred \
             + [store for store in stores.STORES if store not in preferred]

    def resolve_sidecar_for(self, path):
        """Get a sidecar file path for this file

        Returns a tuple (path, is_collection, store) with the pathlib.Path to the sidecar file
        (which may or may not exist), a boolean whether or not the sidecar file is a collection
        file, and the store module that can be used to read/write the metadata to this sidecar.

        May return (None, False, None) in case there is no usable storage. In that case it will
        write a message into the error log, too.
        """
        # find what type of metadata file should be used
        sidecar = None
        is_collection = None
        all_stores = [(store, hasattr(store, 'store'))
                      for store in self.get_preferred_sidecar_stores()]
        usable_stores = [store for store, usable in all_stores if usable]
        if len(usable_stores) == 0:
            return None, False, None

        logger.debug("Resolving sidecar files for %s", path)
        logger.debug(" ... available stores: %s", usable_stores)

        prefer_collection = False

        # find existing sidecar file
        for store, usable in all_stores:
            location = path.parent / (path.stem + store.SUFFIX)
            if location.is_file() and usable:
                sidecar = location
                break

        logger.debug(" ... any direct sidecar? %s", sidecar)

        # if there was none, find existing collection sidecar file
        if sidecar is None:
            for store, is_usable in all_stores:
                for collection_name in self.collection_metadata:
                    if not collection_name.endswith(store.SUFFIX):
                        continue
                    location = path.parent / collection_name
                    logger.debug(" ... trying at %s", location.name)
                    if location.is_file():
                        logger.debug(" ... found a collection sidecar file at %s", location)
                        if is_usable:
                            sidecar = location
                            is_collection = True
                            break
                        logger.debug(" ... but it cannot be used")
                        prefer_collection = True
                if sidecar is not None:
                    break
        # still none? just take the first preferred sidecar store and create a sidecar file
        if sidecar is None:
            if prefer_collection:
                sidecar_name = self.collection_metadata[0]
                is_collection = True
            else:
                sidecar_name = path.stem
            sidecar = path.parent / (sidecar_name + usable_stores[0].SUFFIX)

        return sidecar, is_collection, stores.BY_SUFFIX[sidecar.suffix]

    def load_mimetypes(self):
        """Load the user-configured extra mimetypes"""
        extra_mimetypes = [str(pathlib.Path(fn.strip()).expanduser().resolve())
                           for fn in self.list(SECTION_GENERAL, CONFIG_MIMETYPES, "", "\n")]
        if len(extra_mimetypes) > 0:
            mimetypes.init(files=extra_mimetypes)

    @staticmethod
    def load_addons():
        """Load the indexer addons"""
        # load indexer addons
        if ADDONSPATH.exists():
            prev_sys_path = sys.path.copy()
            sys.path = [str(ADDONSPATH)]
            for item in ADDONSPATH.iterdir():
                if item.is_file() and item.suffix == '.py':
                    logger.info(f"Loading addon {item.name}")
                    importlib.import_module(item.stem)
            sys.path = prev_sys_path

    def ignore_indexers(self):
        """Remove all indexers that the user configured to be ignored"""
        from metaindex import indexer
        indexer.remove_indexers(self.list(SECTION_GENERAL, CONFIG_IGNORE_INDEXERS, ''))


def load(conffile=None):
    conf = configparser.ConfigParser(interpolation=None)
    conf.read_dict(CONF_DEFAULTS)

    if conffile is not None and not isinstance(conffile, pathlib.Path):
        conffile = pathlib.Path(conffile)
    elif conffile is None:
        conffile = CONFIGFILE
    conffile = conffile.expanduser().resolve()

    if conffile is not None and not conffile.is_file():
        logger.info(f"Configuration file {conffile} not found. "
                     "Using defaults.")
        conffile = None
    if conffile is None and CONFIGFILE.is_file():
        conffile = CONFIGFILE

    if conffile is not None:
        logger.info(f"Loading configuration from {conffile}.")
        conf.read([conffile])

    conf.read([str(pathlib.Path(conf['Include'][key]).expanduser().resolve())
               for key in sorted(conf['Include'])])

    config = Configuration(conf)
    config.load_mimetypes()
    config.load_addons()
    config.ignore_indexers()

    return config
