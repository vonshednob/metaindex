Installing
==========

The easiest way to install *metaindex* is through `PyPi
<https://pypi.org/projects/metaindex/>`_::

  pip install metaindex

*metaindex*'s indexer modules are mostly optional. If you, for example,
want to use metaindex for audio files and PDFs, you will have to install it
like this::

    pip install metaindex[pdf,audio]

or, for the cloned repository::

    pip install .[pdf,audio]

These modules exist for indexing:

 - ``pdf``, for PDF files,
 - ``audio``, any type of audio/music file,
 - ``image``, any type of image file,
 - ``video``, any type of video file (overlaps somewhat with `audio`),
 - ``ebook``, ebooks and comic book formats,
 - ``xdg``, support for XDG (if you use Linux, just add it),
 - ``yaml``, extra metadata in YAML format,
 - ``ocr``, find and extract text from images with tesseract (you must have tesseract installed for this to work).

In case you just want everything, this is your install command::

    pip install .[all]


If you’d rather download the source from the authoritative website, visit
https://vonshednob.cc/metaindex/releases.html and get the signed source
tarball from there.

