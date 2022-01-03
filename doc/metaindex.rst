======
metaindex
======
---------------------------
document search by metadata
---------------------------

Synopsis
========

::

  metaindex [-h] [--list] [-l loglevel] [-c configuration file] {find,index,fs}


Description
===========

With metaindex you can find files on your disk based on their metadata, like
the title of a PDF, the keywords of an ebook, or the model of a camera that
a photo was taken with.

The following types of files are supported by default:

 - Images (anything that has EXIF, IPTC, or XMP information),
 - Audio (audio file formats that have ID3 header or similar),
 - Video (most video file formats have an ID3 header),
 - PDF,
 - ebooks (epub natively, calibre metadata files are understood, too).

More file types can be supported through the use of `Addons`_.

User provided extra metadata is supported, if it’s provided in the same
directory as the file and the metadata file is ``.metadata.json``. See
`Extra Metadata`_ below for more details.


Options
=======

General parameters are:

  ``-c configuration file``
    Use this configuration file instead of the one from the default
    location.

  ``-h``
    Show the help.

  ``-l loglevel``
    Set the level of details shown in logging. Your options are ``fatal``,
    ``error``, ``warning``, ``info``, and ``debug``. Defaults to ``warning``.

  ``--list``
    List all available indexers and exit.

metaindex operates in one of the modes ``index`` or ``find``.

If you want to try the experimental filesystem mode, there is also ``fs``.


Find
----

This is the main operation used to search for files::

  metaindex find [-l directory] [-f [-k]] [-t [tags]] [--] [search queries]

The options to this command are

  ``-t [tags]``
    Metadata tags that you wish to see per found file.

  ``-l directory``
    If this option is provided, metaindex will create this directory (or use
    the existing directory only if it is empty) and create a symbolic link
    to all files that matches this search.

  ``-f``
    Enforce the use of ``-l``’s ``directory``, even if it is not empty.
    Still, metaindex will only work with that directory if it contains only
    symbolic links (e.g. a previous search result)!
    If ``-f`` is provided, all symbolic links in ``directory`` will be
    deleted and the links of this search will be put in place.

  ``-k``
    When you use ``-l`` and ``-f``, ``-k`` will keep all existing links in
    the search directory. That means you can accumulate search results in
    one directory.

  ``search queries``
    The terms to search for. If left empty, all files will be found. See
    below in section `Search Query Syntax`_ for the details on search
    queries.
    If the search query is only given as ``-``, metaindex will read the search
    query from stdin.


Index
-----

This is the operation to index files and store that information in the
cache::

  metaindex index [-C] [-r] [-p processes] [-i [paths]]

The options to this command are

  ``-C``
    Clear the cache. If combined with other options, the flushing of the
    cache will happen first.

  ``-m``
    Remove missing files. When a file, that's in the index, can not be
    found on disk anymore, it will be removed when this option is enabled.
    By default this option is disabled.

  ``-i [paths]``
    Run the indexer on these paths. If no paths are provided, all paths in
    the cache are revisited and checked for changes.
    If ``paths`` is ``-``, the list of files will be read from stdin, one
    file per line.

  ``-p processes``
    By default metaindex will run as many indexer processes in parallel as
    CPUs are available on the computer. This parameter allows you to define
    how many indexers may be run at the same time.

  ``-r``
    Run the indexer recursively. That means to visit all files in all
    subdirectories of the paths in the ``-i`` parameter.


Filesystem (fs)
---------------

On Linux you can try the experimental feature of mounting a FuseFS that
will give you a structured access to your files through their metadata::

  metaindex fs [command] [mount point]

The only supported command so far is ``mount``.

It is very experimental and not very useful, but at the same time will not
break any of your files as it only provides a read-only view on your tagged
files.


Files
=====

metaindex is controlled through a configuration file and caches metadata in a
cache file.


Cache file
----------

The cache file is usually located in ``~/.cache/metaindex/index.db``, but that
location is configurable.


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
    When looking for sidecar metadata files (see `Extra Metadata`_), also
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

    See below in `Extra Metadata`_ for more details.

  ``ignore-dirs``
    What folders (and their subfolders) to ignore entirely. One folder per
    line. Defaults to ``.git, .stfolder, System Volume Information, __MACOSX``.
    
    You can use unix-style path patterns, like ``_tmp*``.

  ``ignore-files``
    What files to ignore entirely. One file name pattern per line. The
    default is: ``*.aux, *.toc, *.out, *.log, *.nav, *.exe, *.sys, *.bat, *.ps, *.sh, *.fish, *~, *.swp, .bak, *.sav, *.backup``.

    The can use unix-style patterns, like ``*.tmp``.

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


Search Query Syntax
===================

If the search term only contains a simple word, like ``albatross``, all
files will be found that contain this word in any metadata field.

To search for a phrase containing spaces, you have to enclose the phrase in
blockquotes or single quotes, like ``"albatross flavour"``.

To search for "albatross" in a specific metadata field, like in the title,
you have to search for ``title:albatross``. Again, the phrase search
requires quotes: ``title:"albatross flavour"``.

You can search files by the existance of a metadata tag by adding a ``?``
after the name of the metadata tag. For example, to find all files that
have the ``resolution`` metadata tag: ``resolution?``.

When the search includes the tag name, you have to provide the full
case-sensitive name of the tag. ``artist`` and ``Artist`` are very
different tag names and just searching for ``artist:tim`` when you mean to
search for ``albumartist`` will not result in the same search results.

Have a look at the `Synonyms`_ feature to find out how to search
conveniently for more complex tag names.

When searching for multiple terms, you can choose to connect the terms with
``and`` or ``or``. ``and`` is the default if none is provided, so these two
search queries, to find all photos made with a Canon camera and with a
width of 1024 pixels, are the same::

  resolution:1024x Exif.Image.Model:canon

  resolution:1024x and Exif.Image.Model:canon

To search for all pictures that are made with a Canon camera or have that
width, you have to use ``or``::

  resolution:1024x or Exif.Image.Model:canon


Metadata tags
-------------

These metadata tags are always available:

  ``last_accessed``
    A timestamp when the file was accessed the last time (if the OS
    supports it).

  ``last_modified``
    A timestamp when the file was modified the last time (if the OS
    supports it).

  ``filename``
    The name of the file on disk including extensions.

  ``size``
    The file size in bytes.

  ``mimetype``
    The mimetype of the file, if it could be detected.


Extra Metadata
==============

Not all filetypes support metadata (plain text files, for example) and
using extra files on the side (but in the same directory as the file to be
tagged) is used. These files on the side are called "sidecar files".

Sidecar files are expected to have the same filename as the file that they
are describing, but with a different extension, based on how the
description is provided. So, if you want to add additional metadata to your
``moose.jpg``, you could create a ``moose.json`` sidecar file or a
``moose.opf`` file.

All metadata provided by extra sidecar files is cached with the ``extra.``
prefix. For example, if your metadata file tags a file with ``title``, you
can search for it by looking for ``extra.title``.

metaindex supports sidecar files in JSON format like this when the file is
used for several files::

  {
   "file.ext": {
    "title": "An example file",
    "authors": ["dr Gumby", "The Bishop"],
    "Xmp.dc.title": null
   }
  }

If you set the metadata for only one file, for example
``a_long_story.pdf``, this could be the content of the corresponding sidecar file
``a_long_story.json``::

  {
    "title": [
      "long story, A",
      "A long story"
    ],
    "date": 2012-05-01
  }

**Beware**, if you create a sidecar metadata file with the above content
and name it ``metadata.json`` (or any other filename that’s covered by the
``collection-metadata`` option), all files in the folder will be given
these metadata tags, as if you had used the ``*`` notation! See `Collection
Metadata`_ for details.

The special value of ``null`` allows you to ignore a metadata tag from that
file, i.e. if that file has the ``Xmp.dc.title`` tag, it will be ignored.

Calibre style sidecar files, usually called ``metadata.opf`` are also
supported.

If you installed metaindex with the ``[yaml]`` option, YAML style metadata
files are supported, too. An example of a YAML sidecar file for 


Collection Metadata
-------------------

Sometimes all files in a directory should receive the same set of metadata.
This is called "Collection metadata" and can be accomplished in JSON
sidecar files (like ``.metadata.json``) by adding an entry ``"*"``.

Suppose you have this ``.metadata.json`` in a directory with two files
other ``file.tif`` and ``other.csv``::

  {
    "*": {
      "tags": ["tag1", "tag2"]
    },
    "file.tif": {
      "tags": ["tag3"]
    }
  }

In this example all (both) files in the folder will receive the tags
``tag1`` and ``tag2``, but only ``file.tif`` will have all three tags.

**Beware**, if you leave the ``*`` out and do not specify any metadata
specific to any file, metaindex will assume you meant that this metadata
applies to all files in the directory. Like this::

  {
   "tags": ["tag1", "tag2"],
   "author": "Arthur Pewty"
  }

The above example is equivalent to::

  {
   "*": {
    "tags": ["tag1", "tag2"],
    "author": "Arthur Pewty"
   }
  }

For collection metadata to work properly, the `General`_ option
``collection-metadata`` must be set to the names of sidecar files that are
allowed to define collection metadata.

By default files like ``.metadata.json``, and ``metadata.opf``
are expected to contain extra metadata (see `General`_ options above).
If your metadata files are called
differently, for example ``meta.json`` and ``.extra.json``, you can
configure that in the metaindex configuration file::

  [General]
  collection-metadata = meta, .extra

The filenames listed in ``collection-metadata`` will be excluded from indexing,
so they will not show up when you search for them (e.g. via ``metaindex find
filename:metadata``)!

If metaindex has been installed with the ``yaml`` option, metadata
files in the yaml format are understood and used.


Recursive Collection Metadata
-----------------------------

If you want to apply the collection metadata not only to the files of the
sidecar’s directory, but also in all subdirectories, you can use the
"recursive collection metadata" ``"**"``.

This is useful if you already have your data structured in directories, for
example in this way: ``pictures/nature/animals/duck.jpg``.

Here you could add a ``.metadata.json`` file in the ``nature`` directory
with this recursive directive::

  {
    "**": {
      "tags": ["nature"]
    }
  }

Now not only the files in ``nature`` are tagged as ``nature``, but also
all files in ``animals``.

You can disable this functionality entirely by setting the `General`_
option ``recursive-collection-metadata`` to an empty string::

  [General]
  recursive-collection-metadata =

**Caveat**: you can not defined both, a recursive and a non-recursive set
of collection metadata in the same directory::

  {
    "*": {
      "description": "BROKEN EXAMPLE: this does not work!"
    },
    "**": {
      "title": "BROKEN EXAMPLE! 'title' AND 'description' will be applied to all
      subdirectories!"
    }
  }


Indexers
========

To see all available indexers, run ``metaindex --list``. None of the
built-in indexers require or have any configuration options except for the
``rule-based`` indexer.

Rule Based Indexer
------------------

The rule based indexer is used to determine metadata tags from the fulltext
of an indexed document. For example a scanned bill might contain a date or
transaction number. Or a PDF document might contain an account number.

To function at all the rule based indexer requires that the
``ocr.fulltext`` metadata tag contains the fulltext of the document.
That means you will have to enable the ``fulltext`` configuration option.
The ``ocr`` configuration option is also required if you wish to run this
indexer on images (e.g. scanned documents).

Example
~~~~~~~

Suppose the full text of such a scanned document looks like this::

    Invoice #12345

    2012-04-13

    Big Corp Inc.   Your Money Is Our Future


    Dear customer,
    Thank you for ordering at Big Corp. Please pay us now this ridiculous
    amount of money by 2012-05-30: $500.20.

    Thanks,
     Big Corp CEO Whatstheirname

You could write a rule file like below and save it as ``big-corp.txt``::

    match /Big Corp Inc/ and /Invoice/
      set date /([0-9]{4}-[01][0-9]-[0-3][0-9])/
      set invoicenr /Invoice #([0-9]+)/
      set issuer "Big Corp Inc."

See below for the full syntax of a rule file.

Now you tell metaindex about the rule file by adding it to your
configuration file::

    # snippet of the metaindex configuration file
    [Indexer:rule-based]
    some-rules = ~/big-corp.txt

You will have to provide the full path to the rule file, otherwise
metaindexer will likely not find it.

Now you are ready to go! Next time you run the metaindexer, it will add the
``issuer`` and ``invoicenr`` to the meta data of the scanned document
automatically.


Rule File Syntax
~~~~~~~~~~~~~~~~

A rule file is a plain text file. Empty lines and lines starting with ``#`` or
``;`` are ignored::

    # a comment in a rule file
    ; another comment

    # the line above is also ignored, because it's empty


Match Directives
^^^^^^^^^^^^^^^^

Rules are guarded by match directives that define whether or not a set of
rules should apply to a document. A match directive is started with the
keyword ``match`` followed by one or more regular expressions, optionally
separated by ``and`` for readability::

    # Examples of match directives

    # matches a document that has "Big Corp" in its fulltext
    match /Big Corp/
    
    # matches a document that has the words "Big" and "Corp" in it,
    # but not only "Big Corp"
    match /Big/ and /Corp/

    # the same as above, just without the "and"
    match /Big/ /Corp/

    # match case insensitive
    match /big corp/i

The regular expressions for ``match`` directives must be surrounded by fencing
characters. ``/`` is most commonly used, but any will do, really::

    # other fencing characters are allowed
    match "Big" and ,Corp,

Only when the regular expressions of a ``match`` directive are found in a
document, the subsequent ``set`` and ``find`` directives are applied.
``set`` and ``find`` directives are usually indented, but that’s not a
requirement, only a visual help.


Set Directives
^^^^^^^^^^^^^^

A ``set`` directive is used to set a tag for a document. It’s following the
syntax ``set <tag name> <value>``.

If the tag name contains spaces, you must surround the tag name with ``"``.

The value can be either of two things:

 1. A regular expression,
 2. A single line text.

A regular expression must be surrounded by ``/`` characters. A single line of
text can be surrounded by ``"`` characters (for example to allow for a text with
a leading ``/`` or with trailing whitespace characters)::

    # examples of valid set directives
    match /Big Corp/
      set issuer "Big Corp"
      set type Annoying invoice
      set "silly amount" /(\$[0-9]+)/

Similar to the ``match`` directive you can set regular expressions to be case
insensitive::

    # example of a case insensitive set directive
    match /Big Corp/
      set issuer /(big [a-z]+)/i

Inside single lines of text you may refer to local variables as defined by
``find`` like this::

    # example of referring to a local variable
    match /Big Corp/
      find amount /\$([0-9]+)/
      set money "{amount} USD"

You can have multiple ``set`` directives that assign a value to the same tag::

    # example of several set directives
    match /Big Corp/ and /Invoice/
      set tags invoice
      set tags /your product: ([a-z ]+)/i


Find Directives
^^^^^^^^^^^^^^^

A ``find`` directive can be used to extract parts of the fulltext into a variable
that’s local to this match directive and can be reused in ``set``.

``find`` directives have the syntax ``find <name> /<regular expression>/``.
The regular expression must be surrounded by ``/``.

Just like regular expressions in ``match`` and ``set`` directives, you can set the
regular expression here to be case insensitive by appending `i` after the last
``/``::

    # example of case insensitive find directive
    match /Big Corp/
      find issuer /(big [a-z]+)/i
      set issuer "From {issuer}"



Addons
======

You can extend the capabilities of metaindex to index file types that are
not supported at the moment by writing addons.

These should be placed in ``~/.local/share/metaindex/addons/`` and will be
loaded upon start of metaindex.

**Beware** that these addons can do whatever they want. They might encrypt
all your files or even first upload them to the internet. **Never copy
untrusted python files into the addons folder.**

Addons must be derived from ``metaindex.indexer.Indexer`` and be
decorated with ``@registered_indexer``. Here is a very stupid example of a
working indexer that adds the subject ``stupid`` to every file::

    from multidict import MultiDict

    from metaindex.indexer import Indexer, registered_indexer, Order


    @registered_indexer
    class StupidIndexer(Indexer):
        NAME = 'stupid'
        ACCEPT = '*'
        ORDER = Order.FIRST
        PREFIX = 'extra'

        def run(self, path, info, last_cached):
            return True, MultiDict({self.PREFIX + '.subject': 'stupid'})

``path`` is the ``pathlib.Path`` to the file that is to be indexed,
``info`` is a multidict of already obtained metadata from previously run
indexers, and ``last_cached`` is the metadata information of ``path`` as it
is currently in the cache (in case you need to compare to previous values).

If you want your indexer to only run if the file at ``path`` has changed
since the last run of the indexers (any indexers, really), you can use the
``@only_if_changed`` decorator.

If your indexer can extract the full (human readable) text from the file,
be sure to query ``self.should_fulltext(path)`` if you should do it.

The same goes for OCR'ing images of the file being indexed. Please query
``self.should_ocr(path)`` if the user really wanted this to go through OCR.

Any extracted fulltext should by convention be stored in a metadata tag
that ends with ``.fulltext``, e.g. ``msdoc.fulltext`` if your indexer uses
the prefix ``msdoc``.

Please see ``metaindex.indexer.Indexer`` for more details and
``metaindex.indexers`` for existing indexers as examples.


Usage Examples
==============

Index some directories
----------------------

To index you ``Documents`` and ``Pictures`` folder recursively::

  metaindex index -r -i ~/Documents ~/Pictures


Reindex all files
-----------------

To only update the metadata from all known files::

  metaindex index -i


Find all files
--------------

List all files that are in cache::

  metaindex find


Find file by mimetype
---------------------

Searching for all ``image/*`` mimetypes can be accomplished by this::

  metaindex find mimetype:^image/


Listing metadata
----------------

To list all metadata tags and values of all odt files::

  metaindex find -t -- "filename:odt$"

List the resolutions of all files that have the ``resolution`` metadata tag::

  metaindex find -t resolution -- "resolution?"


Bugs
====

Surely. Please report anything that you find at
https://github.com/vonshednob/metaindex or via email to the authors.

