"""Various indexers for common formats"""
import datetime
import io

try:
    import pdfminer
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
    from pdfminer.converter import PDFConverter, TextConverter
    from pdfminer.pdfpage import PDFPage
    from pdfminer.layout import LTImage, LTPage, LTFigure, LAParams
except ImportError:
    pdfminer = None

try:
    import PIL
    import PIL.Image
except ImportError:
    PIL = None

from metaindex import logger
from metaindex import shared
from metaindex.indexer import IndexerBase, only_if_changed


if pdfminer is not None:
    class PdfMinerIndexer(IndexerBase):
        """PDF file indexer using PdfMiner"""
        NAME = 'pdfminer'
        ACCEPT = ['application/pdf']
        PREFIX = ('pdf', 'ocr')

        PDF_METADATA = ('title', 'author', 'creator', 'producer', 'keywords',
                        'manager', 'status', 'category', 'moddate', 'creationdate',
                        'subject')

        @only_if_changed
        def run(self, path, info, _):
            logger.debug(f"[pdfminer] processing {path.name}")

            try:
                fp = open(path, 'rb')
            except OSError:
                return

            ocr_result = [False, '', '']

            # basic document info
            try:
                parser = PDFParser(fp)
                pdf = PDFDocument(parser)
            except KeyboardInterrupt:
                fp.close()
                raise
            except:
                fp.close()
                return

            try:
                pdf_pages = list(PDFPage.get_pages(fp, set(), check_extractable=False))
                logger.debug(f"[pdf-miner] {len(pdf_pages)} pages")
            except:
                pdf_pages = []

            if self.should_ocr(path):
                # OCR every image
                rmngr = PDFResourceManager(caching=True)
                device = MyImageReader(ocr_result, rmngr, self.ocr)
                interpreter = PDFPageInterpreter(rmngr, device)
                try:
                    for page in pdf_pages:
                        interpreter.process_page(page)
                except KeyboardInterrupt:
                    fp.close()
                    raise
                except Exception as exc:
                    logger.warning("[pdfminer] OCR in PDF died: %s", exc)

            if len(pdf_pages) > 0:
                info.add('pdf.pages', len(pdf_pages))

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
                    fulltext = text_output.getvalue().replace('\0', '').strip()
                    info.add('pdf.fulltext', fulltext)
                    logger.debug(f"[pdfminer] got fulltext: {fulltext}")
                except KeyboardInterrupt:
                    fp.close()
                    raise
                except Exception as exc:
                    logger.warning(f"[pdfminer] could not extract fulltext: {exc}")

            fp.close()

            if ocr_result[0]:
                info.add('ocr.language', ocr_result[1])
                if self.should_fulltext(path) and len(ocr_result[2]) > 0:
                    info.add('ocr.fulltext', ocr_result[2])

            # merge the metadata into the result multidict
            if len(pdf.info) > 0:
                for field in pdf.info[0].keys():
                    if not isinstance(field, str):
                        logger.debug("[pdfminer] Unexpected type for info field key: %s",
                                     type(field))
                        continue
                    if field.lower() not in self.PDF_METADATA:
                        logger.debug("[pdfminer] Ignoring %s key", field)
                        continue

                    raw = pdf.info[0][field]
                    value = None

                    if isinstance(raw, bytes):
                        value = shared.to_utf8(raw)
                        if value is None:
                            continue
                    elif isinstance(raw, str) and len(raw.strip()) > 0:
                        value = raw.replace('\0', '').strip()
                    else:
                        continue

                    if field.endswith('Date') and value.startswith(':'):
                        try:
                            value = datetime.datetime.strptime(value[:15], ':%Y%m%d%H%M%S')
                        except ValueError:
                            continue

                    if value is not None:
                        info.add('pdf.' + field, value)

    class MyImageReader(PDFConverter):
        """OCR image handler; utility class for PdfMinerIndexer"""
        def __init__(self, output, rdmngr, ocr, **kwargs):
            super().__init__(rdmngr, io.BytesIO(), **kwargs)
            self.ocr = ocr
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
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    logger.error(f"[pdfminer] Could not run OCR on image from PDF: {exc}")

        def ocr_pdf_page(self, stream):
            if PIL is None:
                return

            img_ = PIL.Image.open(io.BytesIO(stream.get_rawdata()))

            result = self.ocr.run(img_)
            if result.success:
                self.output[0] = True
                self.output[1] = result.language
                self.output[2] += result.fulltext + "\n"
