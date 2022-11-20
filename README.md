# metaindex

metaindex allows you to find files based on metadata information.

For example, if you want to find all pictures that are have a certain width,
you could do this:

    metaindex find mimetype:image resolution:1200x

The following file formats are supported out of the box (although they might
need additional python packages, see <#Installation>):

 - images (png, jpg, etc.; whatever is supported by [Pillow](https://python-pillow.org/))
 - audio (mp3, m4a, ogg, etc.; whatever is supported by [mutagen](https://mutagen.readthedocs.io/))
 - OpenDocument (odt, ods, etc.)
 - Office Open XML (docx, pptx, xlsx)
 - pdf
 - html
 - epub
 - [abc](https://abcnotation.com/) music notation
 - cbz (through [ComicInfo.xml](https://github.com/anansi-project/comicinfo))
 - gpx


## Installation

To install metaindex either install it directly through pypi:

    pip install metaindex

Or clone the repository and install that then through pip:

    git clone https://codeberg.org/vonshednob/metaindex
    cd metaindex
    pip install .

Most modules are optional. If you, for example, want to use metaindex for audio
files and PDFs, you will have to install it like this:

    pip install metaindex[pdf,audio]

or, for the cloned repository:

    pip install .[pdf,audio]

These modules exist for indexing:

 - `pdf`, for PDF files,
 - `audio`, any type of audio/music file,
 - `image`, any type of image file,
 - `video`, any type of video file (overlaps somewhat with `audio`),
 - `ebook`, ebooks and comic book formats,
 - `xdg`, support for XDG (if you use Linux, just add it),
 - `yaml`, extra metadata in YAML format,
 - `ocr`, find and extract text from images with tesseract (you must have
   tesseract installed for this to work).

In case you just want everything, this is your install command:

    pip install .[all]

There is also an experimental FuseFS filesystem. To be able to use it, you
will have to specify ``fuse`` as an additional module:

    pip install .[all,fuse]


## Usage

Before you can use metaindex to search for files, you have to initialize the
cache by telling it where your files to index are, for example:

    metaindex index --recursive --index ~/Pictures

Afterwards you can start searching for files by metadata, like this:

    metaindex find 


## Searching

Search queries for use with `metaindex find` allow you to search

 - for files that have a metadata tag: `metaindex find resolution?`
 - for files that have a metadata tag with a certain value: `metaindex find title:"dude, where is my car"`
 - for files that have any metadata tag with a certain value: `metaindex find "just anything"`

Each value that you provide is actually a case insensitive regular expression.


## Usage from Python

To use the metaindex infrastructure from Python, you should instantiate a
`Cache` (you should use `MemoryCache` though to get the best performance; all
three classes, `Cache`, `ThreadedCache`, and `MemoryCache` provide the same
interface) and run queries against it (with `find`).

`Cache.find` will return an iterable of `Cache.Entry` instances, consisting of

 - `path`, the location in the file system where that file was last seen
 - `metadata`, a multidict of all metadata
 - `last_modified`, the timestamp when the file was last modified on disk (to
   the knowledge of the cache)

To use the user's preferences, it's a good idea to load their configuration.
Here's an example snippet that'll do both things:

    from metaindex.configuration import load
    from metaindex.cache import MemoryCache

    config = load()
    cache = MemoryCache(config)

    # memory cache can load in the background, so before the *first* query
    # you could consider waiting for it to load all entries
    cache.wait_for_reload()

    searchquery = 'mimetype:image title?'

    for entry in cache.find(searchquery):
        print(entry.path)

## Where is the code?

The original idea to keep this project at github was not the greatest idea
and I’ve moved it over to
[codeberg](https://codeberg.org/vonshednob/metaindex).

This placeholder remains though to keep track of the remaining issues (and
be able to inform the folks that raised the issues).

However, just like with any other open source project, you’re invited to
participate in pter’s development. Any contribution is welcome, from bug
reports to pull requests/sending of patches!


## License

MIT.
