"""Various indexers for common formats"""
import datetime
import io
import zipfile
import re

import multidict

try:
    import pyexiv2
except ImportError:
    pyexiv2 = None

try:
    import PIL
    import PIL.Image
except ImportError:
    PIL = None

try:
    import mutagen
except ImportError:
    mutagen = None

try:
    import pdfminer
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfdocument import PDFDocument
except ImportError:
    pdfminer = None

from metaindex import logger
from metaindex import shared
from metaindex import json
from metaindex import opf
from metaindex import configuration
from metaindex.indexer import registered_indexer, Indexer, Order, only_if_changed
from metaindex.ruleindexer import RuleIndexer as _

try:
    from metaindex import yaml
except ImportError:
    yaml = None


if pyexiv2 is not None:
    @registered_indexer
    class Exiv2Indexer(Indexer):
        NAME = 'exiv2'
        ACCEPT = ['image/', 'video/']
        PREFIX = ('Xmp', 'Exif', 'Iptc')

        @only_if_changed
        def run(self, path, info, last_cached):
            logger.debug(f"[image, exiv2] processing {path.name}")

            try:
                meta = pyexiv2.core.Image(str(path))
            except:
                return False, {}

            result = multidict.MultiDict()
            try:
                result.extend(meta.read_exif())
            except:
                pass

            try:
                result.extend(meta.read_iptc())
            except:
                pass

            try:
                result.extend(meta.read_xmp())
            except:
                pass

            meta.close()
            return True, result


if mutagen is not None:
    @registered_indexer
    class MutagenIndexer(Indexer):
        NAME = 'mutagen'
        ACCEPT = ['audio/', 'video/']
        PREFIX = ('id3', 'audio')

        def run(self, path, info, last_cached):
            logger.debug(f"[mutagen] processing {path.name}")

            try:
                meta = mutagen.File(path, easy=True)
            except:
                return False, {}

            result = multidict.MultiDict()

            if meta is not None:
                for key in meta.keys():
                    result.extend([('id3.' + key, value) for value in meta[key]])
                if hasattr(meta, 'info') and hasattr(meta.info, 'length'):
                    result.add('audio.length', meta.info.length)

            return True, result


if PIL is not None:
    @registered_indexer
    class PillowIndexer(Indexer):
        NAME = 'pillow'
        ACCEPT = ['image/']
        PREFIX = ('ocr', 'image')

        @only_if_changed
        def run(self, path, info, last_cached):
            logger.debug(f"[image, pillow] processing {path.name}")

            try:
                meta = PIL.Image.open(path)
            except:
                return False, {}

            result = {}
            if meta is not None:
                result = {'image.resolution': "{}x{}".format(*meta.size)}
                if self.should_ocr(path):
                    ocr = self.ocr.run(meta)
                    if ocr.success:
                        result['ocr.language'] = ocr.language
                        if self.should_fulltext(path) and len(ocr.fulltext) > 0:
                            result['ocr.fulltext'] = ocr.fulltext
                meta.close()

            return True, result


if pdfminer is not None:
    @registered_indexer
    class PdfMinerIndexer(Indexer):
        NAME = 'pdfminer'
        ACCEPT = ['application/pdf']
        PREFIX = ('pdf', 'ocr')

        PDF_METADATA = ('title', 'author', 'creator', 'producer', 'keywords',
                        'manager', 'status', 'category', 'moddate', 'creationdate',
                        'subject')

        @only_if_changed
        def run(self, path, info, last_cached):
            logger.debug(f"[pdfminer] processing {path.name}")

            try:
                fp = open(path, 'rb')
            except OSError:
                return False, {}

            from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
            from pdfminer.converter import PDFConverter, TextConverter
            from pdfminer.pdfpage import PDFPage
            from pdfminer.layout import LTImage, LTPage, LTFigure, LAParams

            run_ocr = self.ocr.run
            ocr_result = [False]

            class MyImageReader(PDFConverter):
                def __init__(self, output, rdmngr, **kwargs):
                    super().__init__(rdmngr, io.BytesIO(), **kwargs)
                    self.output = output
                    self.output.append(False)
                    self.output.append("")
                    self.output.append("")

                def receive_layout(self, ltpage):
                    if isinstance(ltpage, (LTFigure, LTPage)):
                        for obj in ltpage:
                            self.receive_layout(obj)
                    if isinstance(ltpage, LTImage):
                        try:
                            self.ocr_pdf_page(ltpage.stream)
                        except Exception as exc:
                            logger.error(f"[pdfminer] Could not run OCR on image from PDF: {exc}")

                def ocr_pdf_page(self, stream):
                    img_ = PIL.Image.open(io.BytesIO(stream.get_rawdata()))

                    result = run_ocr(img_)
                    if result.success:
                        self.output[0] = True
                        self.output[1] = result.language
                        self.output[2] += result.fulltext + "\n"

            # basic document info
            try:
                parser = PDFParser(fp)
                pdf = PDFDocument(parser)
            except:
                fp.close()
                return False, {}

            try:
                pdf_pages = [page for page in PDFPage.get_pages(fp, set(), check_extractable=False)]
                logger.debug(f"[pdf-miner] {len(pdf_pages)} pages")
            except:
                pdf_pages = []

            if self.should_ocr(path):
                # OCR every image
                rmngr = PDFResourceManager(caching=True)
                device = MyImageReader(ocr_result, rmngr)
                interpreter = PDFPageInterpreter(rmngr, device)
                try:
                    for page in pdf_pages:
                        interpreter.process_page(page)
                except Exception as exc:
                    logger.warning(f"[pdfminer] OCR in PDF died: {exc}")

            result = multidict.MultiDict()

            if len(pdf_pages) > 0:
                result.add('pdf.pages', len(pdf_pages))

            logger.debug(f"[pdfminer] fulltext? {self.should_fulltext(path)}")
            if self.should_fulltext(path) and not fp.closed:
                try:
                    laparams = LAParams()
                    laparams.all_texts = True
                    laparams.detect_vertical = True
                    rmngr = PDFResourceManager(caching=True)
                    text_output = io.StringIO()
                    device = TextConverter(rmngr, text_output, laparams=laparams, imagewriter=None)
                    interpreter = PDFPageInterpreter(rmngr, device)
                    for page in pdf_pages:
                        logger.debug(f"[pdfminer] processing {page}")
                        interpreter.process_page(page)
                    # TODO: some preprocessing of the result might be required
                    #       like replacing weird unicodes with ascii equivalents
                    #       or stripping multiple newlines
                    result['pdf.fulltext'] = text_output.getvalue().replace('\0', '').strip()
                    logger.debug(f"[pdfminer] got fulltext: {result['pdf.fulltext']}")
                except Exception as exc:
                    logger.warning(f"[pdfminer] could not extract fulltext: {exc}")

            fp.close()

            if ocr_result[0]:
                result.add('ocr.language', ocr_result[1])
                if self.should_fulltext(path) and len(ocr_result[2]) > 0:
                    result.add('ocr.fulltext', ocr_result[2])

            # merge the metadata into the result multidict
            if len(pdf.info) > 0:
                for field in pdf.info[0].keys():
                    if not isinstance(field, str):
                        logger.debug(f"[pdfminer] Unexpected type for info field key: {type(field)}")
                        continue
                    if field.lower() not in self.PDF_METADATA:
                        logger.debug(f"[pdfminer] Ignoring {field} key")
                        continue

                    raw = pdf.info[0][field]
                    value = None

                    if isinstance(raw, bytes):
                        value = shared.to_utf8(raw)
                        if value is None:
                            continue
                    elif isinstance(raw, str) and len(raw.strip()) > 0:
                        value = raw.strip()
                    else:
                        continue

                    if field.endswith('Date') and value.startswith(':'):
                        try:
                            value = datetime.datetime.strptime(value[:15], ':%Y%m%d%H%M%S')
                        except ValueError:
                            continue

                    if value is not None:
                        result['pdf.' + field] = value

            return True, result


@registered_indexer
class EpubIndexer(Indexer):
    NAME = 'epub'
    ACCEPT = ['application/epub+zip']
    PREFIX = ('opf',)

    @only_if_changed
    def run(self, path, info, last_cached):
        logger.debug(f"[epub] processing {path.name}")

        with zipfile.ZipFile(path) as fp:
            files = fp.namelist()
            if 'content.opf' in files:
                with fp.open('content.opf') as contentfp:
                    return True, opf.parse_opf(contentfp.read(), '')
        return False, {}


@registered_indexer
class FileTagsIndexer(Indexer):
    NAME = 'filetags'
    ACCEPT = '*'
    PREFIX = 'filetags'

    TAG_MARKER = ' -- '
    DATE_PATTERN = (re.compile(r'^([0-9]+)-([01][0-9])-([0-3][0-9])'), 10)
    DATE2_PATTERN = (re.compile(r'^([0-9]+)([01][0-9])([0-3][0-9])'), 8)
    DATETIME_PATTERN = (re.compile(r'^([0-9]+)-([01][0-9])-([0-3][0-9])[T_]([0-2][0-9])[._-]([0-6][0-9])'), 16)
    DATETIME2_PATTERN = (re.compile(r'^([0-9]+)([01][0-9])([0-3][0-9])_([0-2][0-9])([0-6][0-9])'), 13)
    DATETIMESEC_PATTERN = (re.compile(r'^([0-9]+)-([01][0-9])-([0-3][0-9])[T_]([0-2][0-9])[._-]([0-6][0-9])[._-]([0-6][0-9])'), 19)
    DATETIMESEC2_PATTERN = (re.compile(r'^([0-9]+)([01][0-9])([0-3][0-9])_([0-2][0-9])([0-6][0-9])([0-6][0-9])'), 15)

    def run(self, path, info, last_cached):
        logger.debug(f"[filetags] Running {path.stem}")
        result = set()
        counter = 0

        success, result = self.extract_metadata(path.stem)

        while path.parent != path:
            path = path.parent
            counter += 1

            if counter > 1:
                break

            success, tags = self.extract_metadata(path.stem)
            result |= {(tag, value) for tag, value in tags if tag in [self.NAME + '.date', self.NAME + '.tags']}

        return len(result) > 0, multidict.MultiDict(list(result))

    def extract_metadata(self, text):
        result = set()
        tags = None

        match, text = self.obtain_datetime(text)

        if match:
            result.add((self.PREFIX + '.date', match))

        # date is a range in the form of YYYY-MM-DD--<some date>
        if match and text.startswith('--'):
            rangeend, text = self.obtain_datetime(text[2:])
            # TODO: do something useful with rangeend

        # find the TAG_MARKER, usually ' -- ', to auto specify tags/subject
        if self.TAG_MARKER in text:
            text, tags = text.split(self.TAG_MARKER, 1)
            result |= {(self.PREFIX + '.tags', tag) for tag in tags.split()}

        if text.startswith('-'):
            text = text[1:]

        if len(text.strip()) > 0 and len(result) > 0:
            # only add the title if anything else was found,
            # otherwise the title is just the filename and that's useless
            result.add((self.PREFIX + '.title', text.strip()))

        return len(result) > 0, result

    def obtain_datetime(self, text):
        match = None
        patterns = [
            self.DATETIMESEC_PATTERN,
            self.DATETIMESEC2_PATTERN,
            self.DATETIME_PATTERN,
            self.DATE_PATTERN,
            self.DATE2_PATTERN,
        ]

        for pattern, length in patterns:
            if len(text) < length:
                continue

            match = pattern.match(text)
            if not match:
                continue

            try:
                match = datetime.datetime(*[int(value) for value in match.groups()])
                text = text[length:]
                break
            except (ValueError, OverflowError):
                match = None
                continue

        return match, text


class CollectionSidecarIndexer(Indexer):
    PREFIX = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.debug(f"Creating a new {self.NAME}")

        # cached metadata for collection metadata, pathlib.Path -> multidict
        self.collection_cache = {}
        self.cached_sidecar_files = set()

        self.collection_metadata = self.cache.config.list(
            configuration.SECTION_GENERAL,
            configuration.CONFIG_COLLECTION_METADATA,
            '')
        self.recursive_metadata = self.cache.config.bool(
            configuration.SECTION_GENERAL,
            configuration.CONFIG_RECURSIVE_EXTRA_METADATA,
            'yes')

    def run(self, path, info, last_cached):
        raise NotImplementedError()

    def find_collection_sidecars(self, path, suffix):
        """Walk upwards the directory structure and yield all existing collection metadata files"""
        sidecars = []
        pathptr = path
        if pathptr.is_file():
            pathptr = path.parent
        while True:
            for filename in self.collection_metadata:
                sidecar = pathptr / (filename + suffix)
                if sidecar.exists():
                    sidecars.append(sidecar)
            if not self.recursive_metadata or pathptr == pathptr.parent:
                break
            pathptr = pathptr.parent

        return sidecars

    def cache_collection_sidecars(self, path, store):
        """Fill the cache with the sidecar files' contents"""
        assert self.PREFIX is not None
        for sidecar in self.find_collection_sidecars(path, store.SUFFIX):
            if sidecar in self.cached_sidecar_files:
                continue
            self.cached_sidecar_files.add(sidecar)

            self.collection_cache[sidecar.parent] = multidict.MultiDict()
            for filepath, extra in store.get_for_collection(sidecar, self.PREFIX+'.').items():
                self.collection_cache[filepath] = extra

    def get_collection_metadata(self, path, suffix):
        meta = multidict.MultiDict()

        for sidecar in reversed(self.find_collection_sidecars(path, suffix)):
            if sidecar.parent not in self.collection_cache:
                logger.info("A sidecar file has been added while the indexer was running. "
                            "That file is ignored until the next rerun.")
                continue
            extra = self.collection_cache[sidecar.parent]
            if sidecar.parent != path.parent and \
               not (self.recursive_metadata and extra.get(shared.IS_RECURSIVE, False)):
                continue
            meta.extend(extra)

        if path in self.collection_cache:
            meta.extend(self.collection_cache[path])
        meta.popall(shared.IS_RECURSIVE, [])

        return meta

    def run_with_store(self, store, path, info, last_cached):
        assert self.PREFIX is not None
        self.cache_collection_sidecars(path, store)

        extra = self.get_collection_metadata(path, store.SUFFIX)

        # check for direct sidecar file
        sidecar = path.parent / (path.stem + store.SUFFIX)
        if sidecar.is_file():
            extra.extend(store.get(sidecar, self.PREFIX+'.'))
            extra.popall(shared.IS_RECURSIVE, [])

        return len(extra) > 0, extra


@registered_indexer
class JsonSidecarIndexer(CollectionSidecarIndexer):
    NAME = 'json-sidecar'
    ACCEPT = '*'
    PREFIX = 'extra'
    ORDER = Order.LAST

    def run(self, path, info, last_cached):
        return self.run_with_store(json, path, info, last_cached)


@registered_indexer
class OpfSidecarIndexer(CollectionSidecarIndexer):
    NAME = 'opf-sidecar'
    ACCEPT = '*'
    PREFIX = 'extra'
    ORDER = Order.LAST

    def run(self, path, info, last_cached):
        self.cache_collection_sidecars(path, opf)
        extra = self.get_collection_metadata(path, opf.SUFFIX)
        return len(extra) > 0, extra


if yaml is not None:
    @registered_indexer
    class YamlSidecarIndexer(CollectionSidecarIndexer):
        NAME = 'yaml-sidecar'
        ACCEPT = '*'
        PREFIX = 'extra'
        ORDER = Order.LAST

        def run(self, path, info, last_cached):
            return self.run_with_store(yaml, path, info, last_cached)
