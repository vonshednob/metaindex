"""Image/video indexer"""
import datetime

try:
    import pyexiv2
except ImportError:
    pyexiv2 = None

try:
    import PIL
    import PIL.Image
except ImportError:
    PIL = None


from metaindex import logger
from metaindex.indexer import IndexerBase, only_if_changed


if pyexiv2 is not None:
    class Exiv2Indexer(IndexerBase):
        """Image/Video indexer using EXIV2"""
        NAME = 'exiv2'
        ACCEPT = ['image/', 'video/']
        PREFIX = ('xmp', 'exif', 'iptc')

        @only_if_changed
        def run(self, path, metadata, _):
            logger.debug(f"[image, exiv2] processing {path.name}")

            try:
                meta = pyexiv2.core.Image(str(path))
            except:
                return

            result = []
            try:
                result += list(meta.read_exif().items())
            except:
                pass

            try:
                result += list(meta.read_iptc().items())
            except:
                pass

            try:
                result += list(meta.read_xmp().items())
            except:
                pass

            meta.close()

            while len(result) > 0:
                key, value = result.pop(0)
                key = key.lower()

                if key == 'exif.photo.usercomment':
                    if value.startswith('charset='):
                        try:
                            charset, value = value.split(' ', 1)
                            charset = charset.split('=', 1)[1]
                            value = str(bytes(value, 'utf-8'), charset)
                        except ValueError as exc:
                            logger.error(exc)
                if key in ['exif.photo.datetimeoriginal', 'exif.photo.datetimedigitized',
                           'exif.image.datetime']:
                    value = datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')

                if isinstance(value, str) and len(value) == 0:
                    continue
                if isinstance(value, list):
                    result += [(key, v) for v in value]
                    continue
                if isinstance(value, dict):
                    result += [(key, v) for v in value.values()]
                    continue
                metadata.add(key, value)


if PIL is not None:
    class PillowIndexer(IndexerBase):
        """Image indexer using pillow"""
        NAME = 'pillow'
        ACCEPT = ['image/']
        PREFIX = ('ocr', 'image')

        @only_if_changed
        def run(self, path, metadata, _):
            logger.debug(f"[image, pillow] processing {path.name}")

            try:
                meta = PIL.Image.open(path)
            except:
                return

            if meta is not None:
                metadata.add('image.resolution', "{}x{}".format(*meta.size))
                if self.should_ocr(path):
                    ocr = self.ocr.run(meta)
                    if ocr.success:
                        metadata.add('ocr.language', ocr.language)
                        if self.should_fulltext(path) and \
                           len(ocr.fulltext) > 0:
                            metadata.add('ocr.fulltext', ocr.fulltext)
                meta.close()
