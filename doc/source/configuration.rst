Configuration file
------------------

The configuration file is usually located in ``~/.config/metaindex.conf``. An
example of the configuration file is provided in the ``dist`` directory.
The syntax of the file is::

  [Category]
  option = value

There are several categories in the configuration file, the possible
options are described after this list:

 - ``[General]``, general options
 - ``[Synonyms]``, synonyms for tag names
 - ``[Include]``, additional configuration files that have to be included


General
~~~~~~~

  ``cache``
    The location of the cache file. Defaults to
    ``~/.cache/metaindex/index.db``.

  ``recursive-extra-metadata``
    When looking for sidecar metadata files (see Extra Metadata), also
    look in all parent directories for metadata. Defaults to ``yes``.

    This is useful when the file is ``collection/part/file.jpg`` but the
    metadata file is ``collection/.metadata.json`` (and in this metadata
    file the reference is made to ``part/file.jpg``).

  ``collection-metadata``
    Some sidecar files can define metadata that applies to the entire
    collection of files in that directory. This options controls what
    files may define that type of metadata.
    Based on the available metadata storage modules (e.g. JSON, and OPF)
    these names are extended by the corresponding file extensions.
    Defaults to ``.metadata, metadata``.

    That means, with JSON and OPF enabled, that the metadata files
    ``.metadata.json, .metadata.opf, metadata.json, metadata.opf`` are
    considered.

    See below in Extra Metadata for more details.

  ``ignore-dirs``
    What folders (and their subfolders) to ignore entirely. One folder per
    line. Defaults to ``.git, .svn, .hg, .bzr, .stfolder, System Volume Information, __MACOSX``.
    
    You can use unix-style path patterns, like ``_tmp*``.

  ``ignore-files``
    What files to ignore entirely. One file name pattern per line. The
    default is: ``*.aux, *.toc, *.out, *.log, *.nav, *.exe, *.sys, *.bat, *.ps, *.sh, *.fish, *~, *.swp, *.bak, *.sav, *.backup, *.old, *.old, *.orig, *.rej, tags, *.log, *.a, *.out, *.o, *.obj, *.so``.

  ``accept-files``
    What files to consider. One file name pattern by line, like ``*.doc``.

    If you define this, no other files are indexed and ``ignore-files`` will
    not be used.

    By default this is left empty and instead ``ignore-files`` is used.

  ``index-unknown``
    Whether or not to add files to the index for which no meaningful
    metadata could be extracted from the indexers or any sidecar files.

    Defaults to ``yes``.

  ``ignore-tags``
    What (automatically extracted) tags to not add to the cache and thus
    prevent them being searchable. Comma-separated list of the tags.
    Defaults to: ``Exif.Image.StripByteCounts, Exif.Image.StripOffsets``.

  ``ignore-indexers``
    A comma separated list of indexers by name that you do not want to use.
    By default this list is empty.

    Run ``metaindex --list`` to see what indexers will be used by default.

  ``preferred-sidecar-format``
    What file format you prefer for sidecar files. This is the file format
    that will be used by metaindex and other tools when you add/edit
    metadata sidecar files.
    Defaults to: ``.json``

    Other options are ``.opf`` and ``.yaml`` (if you installed the YAML
    dependencies).

  ``mimetypes``
    If you have additional mimetypes that you would like metaindex to know,
    this is the option you can use to point to additional mimetype files.
    To add multiple files, separate them by a newline. No matter what files
    you provide here, you system's mimetype file will always be used.

  ``ocr``
    Whether or not OCR (optical character recognition) should be enabled.
    For this to work you must have installed the ``ocr`` requirements.

    This option can be set to ``yes`` to enable OCR for everything, but you
    can also fine-tune it by setting the option to a list of mimetypes,
    file suffices, or names of indexers that are allowed to run OCR. For
    example ``ocr = .pdf, image/, epub`` will enable OCR for all ``.pdf``
    files, all mimetypes that are of the ``image/*`` type, and for the
    indexer named ``epub``.

    Beware that the ``ocr`` option alone will not extract the full text of
    images or scanned PDFs (but it will attempt to determine the language;
    however the result might be just plain wrong).

    If you just want to disable OCR entirely, set the value to ``no``
    (which is the default).

  ``fulltext``
    Whether or not to extract the fulltext of documents.

    For images (and scanned PDFs), this requires OCR to be enabled, too.

    This option can be set to ``yes`` to enable fulltext extraction for
    every file type, but you can also fine-tune the setting exactly the
    same way as the ``ocr`` option. For example, if you wanted to only do
    fulltext extraction of PDFs and images, you would use ``ocr = .pdf,
    image/``.

    The default is ``no``, so no fulltext will be extracted.


Synonyms
~~~~~~~~

Some metadata fields have less convenient names than others, but might
semantically be the same. For example, ``Xmp.xmp.CreatorTool`` and
``pdf.Creator`` both mean "The program that was used to create this file".

For convenience it is possible to define synonyms, so you only have to
search for ``author`` when you mean to search for ``id3.artist``,
``pdf.Author``, or ``Exif.Image.Artist``.

The section ``[Synonyms]`` in the configuration file is the place to define
these synonyms. Here are the defaults, that you don’t have to set up::

  [Synonyms]
  author = extra.author, extra.artist, id3.artist, pdf.Author, Exif.Image.Artist
  title = extra.title, id3.title, pdf.Title, Xmp.dc.title, extra.opf.title
  tags = extra.tags, pdf.Keywords, pdf.Categories, Xmp.dc.subject, extra.subject, pdf.Subject, opf.subject, extra.opf.subject
  language = opf.language, pdf.Language, Xmp.dc.language, extra.language, extra.opf.language
  series = extra.series
  series_index = extra.series_index


Include
~~~~~~~

You can include additional configuration files (for example to split up
your configuration into multiple files).

All the ``name = path`` entries in the ``[Include]`` section will be loaded
in the alphabetical order of the names.

In this example ``~/.metaindex.conf`` will be loaded and then
``/tmp/metaindex.conf``. Both of course only after the main configuration file::

  [Include]
  xtra = /tmp/metaindex.conf
  extra = ~/.metaindex.conf

Additional ``[Includes]`` in these included configuration files are ignored
though.

