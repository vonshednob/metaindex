# metaindex linemode integration into ranger
import ranger.api
from ranger.core.linemode import LinemodeBase

try:
    from ..ranger_devicons.devicons import devicon
except ImportError:
    devicon = None

from metaindex.cache import Cache


@ranger.api.register_linemode
class MetaIndexLinemode(LinemodeBase):
    name = "metaindex"
    uses_metadata = False

    def __init__(self):
        super().__init__()
        self.cache = Cache()

    def filetitle(self, fobj, metadata):
        meta = self.cache.get(fobj.path)
        icon = "" if devicon is None else devicon(fobj) + " "

        if len(meta) == 0:
            return icon + fobj.relative_path

        return icon + (meta[0][1].get('title', None) or fobj.relative_path)

