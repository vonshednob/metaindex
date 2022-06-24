"""ComicBook indexer

Native support for cbz and cbt files.
"""
import zipfile
import tarfile

try:
    import defusedxml
    from defusedxml import ElementTree as etree
except ImportError:
    defusedxml = None
    from xml.etree import ElementTree as etree

try:
    import unrar
    import unrar.rarfile
except ImportError:
    unrar = None

from metaindex import logger
from metaindex.indexer import IndexerBase


COMICBOOK_PREFIX = 'comicbook'


class ComicBookInfo:
    ROOT_TAG = 'ComicInfo'
    FIELDS = ['Title', 'Series', 'Number', 'Count', 'Volume',
              'AlternateSeries', 'AlternateNumber', 'AlternateCount',
              'Summary', 'Notes', 'Year', 'Month', 'Day', 'Writer',
              'Penciller', 'Inker', 'Colorist', 'Letterer', 'CoverArtist',
              'Editor', 'Translator', 'Publisher', 'Imprint', 'Genre',
              'Tags', 'Web', 'PageCount', 'LanguageISO', 'Format',
              'BlackAndWhite', 'Manga', 'Characters', 'Teams', 'Locations',
              'ScanInformation', 'StoryArc', 'SeriesGroup', 'AgeRating',
              'CommunityRating']


class ArchiveReader:
    def __init__(self, path):
        self.path = path
        self.handle = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def open(self):
        """Open the archive for reading"""
        if self.handle is not None:
            raise RuntimeError("Already opened")
        self.handle = self.do_open()
        return self

    def close(self):
        """Close the archive again"""
        if self.handle is None:
            raise RuntimeError("Not opened")
        self.do_close()
        self.handle = None

    def do_open(self):
        """Actually open the archive and return the filehandle"""
        raise NotImplementedError()

    def do_close(self):
        """Actually close the open file handle"""
        raise NotImplementedError()

    def files(self):
        """Return the list of files in this archive"""
        raise NotImplementedError()

    def read(self, filename):
        """Return the content of filename from the archive as bytes"""
        raise NotImplementedError()


class ComicInfoIndexer(IndexerBase):
    """Abstract indexer for ComicInfo.xml metadata"""
    PREFIX = None
    READER = ArchiveReader

    def run(self, path, metadata, last_cached):
        check_defusedxml()

        with self.READER(path) as archive:
            files = archive.files()
            indexfile = [fname for fname in files
                         if fname.lower() == 'comicinfo.xml']

            if len(indexfile) > 0:
                xmldata = archive.read(indexfile[0])
                self.parse_comicinfo_xml(xmldata, metadata)

    def parse_comicinfo_xml(self, xmldata, metadata):
        """Extract metadata from ComicInfo.xml into metadata"""
        assert isinstance(self.PREFIX, (set, tuple, list))

        root = etree.fromstring(str(xmldata, 'utf-8'))
        if root.tag != ComicBookInfo.ROOT_TAG:
            logger.info("Invalid root tag %s for ComicInfo.xml", root.tag)
            return

        for node in root:
            if node.tag in ComicBookInfo.FIELDS and node.text is not None:
                metadata.add(self.PREFIX[0] + "." + node.tag.lower(),
                             node.text)
            elif node.tag == 'Pages':
                pass  # TODO - do anything useful with pages?
            else:
                logger.info("Unexpected tag %s in comicinfo.xml", node.tag)


class CBZArchiveReader(ArchiveReader):
    """CBZ archive reader"""
    def do_open(self):
        return zipfile.ZipFile(self.path, 'r')

    def do_close(self):
        assert self.handle is not None
        self.handle.close()

    def files(self):
        assert self.handle is not None
        return self.handle.namelist()

    def read(self, filename):
        assert self.handle is not None
        return self.handle.read(filename)


class CBZComicInfoIndexer(ComicInfoIndexer):
    """ComicInfo indexer for cbz files"""
    NAME = 'comicbook-zip'
    ACCEPT = ['.cbz']
    PREFIX = (COMICBOOK_PREFIX,)
    READER = CBZArchiveReader


class CBTArchiveReader(ArchiveReader):
    """CBT archive reader"""
    def do_open(self):
        return tarfile.open(self.path, 'r')

    def do_close(self):
        assert isinstance(self.handle, tarfile.TarFile)
        self.handle.close()

    def files(self):
        assert isinstance(self.handle, tarfile.TarFile)
        return [m.name for m in self.handle.getmembers()]

    def read(self, filename):
        assert isinstance(self.handle, tarfile.TarFile)
        with self.handle.extractfile(filename) as filecontent:
            return filecontent.read()


class CBTComicInfoIndexer(ComicInfoIndexer):
    """ComicInfo indexer for cbt files"""
    NAME = 'comicbook-tar'
    ACCEPT = ['.cbt']
    PREFIX = (COMICBOOK_PREFIX,)
    READER = CBTArchiveReader


if unrar is not None:
    class CBRArchiveReader(ArchiveReader):
        """CBR archive reader"""
        def do_open(self):
            return unrar.rarfile.RarFile(str(self.path), 'r')

        def do_close(self):
            pass

        def files(self):
            assert self.handle is not None
            return self.handle.namelist()

        def read(self, filename):
            assert self.handle is not None
            return self.handle.read(filename)


    class CBRComicInfoIndexer(ComicInfoIndexer):
        """ComicInfo indexer for cbr files"""
        NAME = 'comicbook-rar'
        ACCEPT = ['.cbr']
        PREFIX = (COMICBOOK_PREFIX,)
        READER = CBRArchiveReader

else:
    class CBRComicInfoIndexer(IndexerBase):
        NAME = 'comicbook-rar'
        ACCEPT = ['.cbr']
        PREFIX = (COMICBOOK_PREFIX,)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.complained = False

        def run(self, *_):
            if not self.complained:
                self.complained = True
                logger.info("To index CBR files, please install python-unrar")


def check_defusedxml():
    """Check the use of defusedxml"""
    global defusedxml
    if defusedxml is None:
        logger.warning("You are using the unsafe XML parser from python. "
                       "Please consider installing 'defusedxml'.")
        defusedxml = False
