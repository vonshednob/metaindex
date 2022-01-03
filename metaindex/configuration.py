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

CONF_DEFAULTS = {'General': {
                    'cache': str(CACHEPATH),
                    'recursive-extra-metadata': "yes",
                    'collection-metadata': ".metadata, metadata",
                    'ignore-directories': "\n".join(IGNORE_DIRS),
                    'ignore-files': "\n".join(IGNORE_FILES),
                    'accept-files': '',
                    'index-unknown': 'yes',
                    'ignore-indexers': '',
                    'ignore-tags': "Exif.Image.StripByteCounts, Exif.Image.StripOffsets",
                    'ocr': 'no',
                 },
                 'Synonyms': SYNONYMS,
                 'Include': {
                 },
                }


class BaseConfiguration:
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._collection_metadata = None

    @property
    def collection_metadata(self):
        if self._collection_metadata is None:
            lst = self.list('General', 'collection-metadata', None)
            if lst is not None:
                lst = set(sum([[fn + store.SUFFIX for store in stores.STORES]
                               for fn in lst], start=[]))
            self._collection_metadata = lst
        return self._collection_metadata

    @property
    def synonyms(self):
        """Returns a dict of all synonyms and the attributes that they stand for

        E.g. might contain the entry 'title', mapping to ['opf.title', 'id3.title']
        """
        if self._synonyms is None:
            self._synonyms = dict([(name, self.list('Synonyms', name)) for name in self['Synonyms']])
        return self._synonyms

    def is_sidecar_file(self, path):
        """Return True if the file at path is a sidecar file (either collection metadata or not)"""
        if not path.is_file:
            return False
        if path.name in self.collection_metadata:
            return True
        for store in stores.STORES:
            if path.suffix == store.SUFFIX and len([fn for fn in path.parent.iterdir() if fn.is_file() and fn != path and fn.stem == path.stem]) > 0:
                return True
        return False

    def resolve_sidecar_for(self, path):
        """Return the path of the direct sidecar file for the given path

        The returned path may point to a file that does not exist yet!
        """
        if not isinstance(path, pathlib.Path):
            path = pathlib.Path(path).expanduser().resolve()

        if path.is_dir():
            metafilenames = self.list('collection-metadata')
            for metafilename in metafilenames:
                metafilepath = path / metafilename
                if metafilepath.exists():
                    return metafilepath
            if len(metafilenames) > 0:
                return path / metafilenames[0]
            return None

        metafilenames = self.list('')

        return path.parent / metafilename

    def load_mimetypes(self):
        extra_mimetypes = [pathlib.Path(fn.strip()).expanduser().resolve()
                           for fn in self.list('General', 'mimetypes', "", "\n")]
        if len(extra_mimetypes) > 0:
            mimetypes.init(extra_mimetypes)

    def load_addons(self):
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
        from metaindex import indexer
        indexer.remove_indexers(self.list('General', 'ignore-indexers', ''))


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

