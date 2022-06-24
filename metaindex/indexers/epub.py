"""epub indexer"""
import zipfile

from metaindex import logger
from metaindex import opf
from metaindex.indexer import IndexerBase, only_if_changed


class EpubIndexer(IndexerBase):
    """Indexer for epub files"""
    NAME = 'epub'
    ACCEPT = ['application/epub+zip', '.epub']
    PREFIX = ('opf',)

    ROOTFILE_NODE = './/{urn:oasis:names:tc:opendocument:xmlns:container}rootfile'

    @only_if_changed
    def run(self, path, metadata, _):
        logger.debug(f"[epub] processing {path.name}")

        with zipfile.ZipFile(path) as fp:
            files = fp.namelist()
            if not 'META-INF/container.xml' in files:
                return

            opffiles = []
            with fp.open('META-INF/container.xml') as containerfp:
                try:
                    root = opf.ElementTree.fromstring(containerfp.read())
                except KeyboardInterrupt:
                    raise
                except:
                    return
                for node in root.findall(type(self).ROOTFILE_NODE):
                    if 'full-path' not in node.attrib:
                        continue
                    rootfile = node.attrib['full-path']
                    if rootfile.endswith('.opf'):
                        opffiles.append(rootfile)

            for file in opffiles:
                if file not in files:
                    continue
                with fp.open(file) as contentfp:
                    metadata.update(opf.parse_opf(contentfp.read(), 'opf.'))
