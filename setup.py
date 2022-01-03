import setuptools
import pathlib


try:
    import docutils.core
    from docutils.writers import manpage
except ImportError:
    docutils = None
    manpage = None


from metaindex import version


with open('README.md', encoding='utf-8') as fd:
    long_description = fd.read()


with open('LICENSE', encoding='utf-8') as fd:
    licensetext = fd.read()


def compile_documentation():
    htmlfiles = []

    if docutils is None:
        return htmlfiles

    dst = pathlib.Path('./metaindex/docs')
    dst.mkdir(exist_ok=True)
    
    pathlib.Path('./man').mkdir(exist_ok=True)

    man_pter = None

    if None not in [docutils, manpage]:
        for fn in pathlib.Path('./doc').iterdir():
            if fn.suffix == '.rst':
                if fn.stem == 'metaindex':
                    man_pter = str(fn)
                dstfn = str(dst / (fn.stem + '.html'))
                docutils.core.publish_file(source_path=str(fn),
                                           destination_path=dstfn,
                                           writer_name='html')
                htmlfiles.append('docs/' + fn.stem + '.html')

    if man_pter is not None:
        docutils.core.publish_file(source_path=man_pter,
                                   destination_path='man/metaindex.1',
                                   writer_name='manpage')

    return htmlfiles


xdg_reqs = ['pyxdg']
image_reqs = ['pyexiv2', 'pillow']
pdf_reqs = ['pdfminer']
audio_reqs = ['mutagen']
video_reqs = ['mutagen']
ebook_reqs = ['defusedxml']
fuse_reqs = ['trio', 'pyfuse3']
yaml_reqs = ['pyyaml']
ocr_reqs = ['pillow>=6.2.0']
all_reqs = set(sum([xdg_reqs, image_reqs, pdf_reqs, audio_reqs, video_reqs,
                    ebook_reqs, yaml_reqs, ocr_reqs],
                   start=[]))


setuptools.setup(
    name='metaindex',
    version=version.__version__,
    description="Utilities to tag files",
    long_description=long_description,
    long_description_content_type='text/markdown',
    license_file="LICENSE",
    license_files="LICENSE",
    url="https://github.com/vonshednob/metaindex",
    author="R",
    author_email="devel+metaindex@kakaomilchkuh.de",
    entry_points={'console_scripts': ['metaindex=metaindex.main:run']},
    packages=['metaindex'],
    package_data={'metaindex': compile_documentation()},
    data_files=[('share/man/man1', ['man/metaindex.1']),
                ('share/applications', []),
                ('share/doc/metaindex', ['misc/metaindex.conf'])],
    install_requires=['multidict'],
    extras_require={'xdg': xdg_reqs,
                    'image': image_reqs,
                    'pdf': pdf_reqs,
                    'audio': audio_reqs,
                    'video': video_reqs,
                    'ebook': ebook_reqs,
                    'yaml': yaml_reqs,
                    'fuse': fuse_reqs,
                    'ocr': ocr_reqs,
                    'all': all_reqs},
    python_requires='>=3.0',
    classifiers=['Development Status :: 3 - Alpha',
                 'Environment :: Console',
                 'Intended Audience :: End Users/Desktop',
                 'Intended Audience :: Developers',
                 'License :: OSI Approved :: MIT License',
                 'Natural Language :: English',
                 'Programming Language :: Python :: 3',
                 'Topic :: Text Processing :: Indexing',])

