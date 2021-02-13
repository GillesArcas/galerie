import glob
import os
from setuptools import setup


print('PATH:', os.path.dirname(os.path.realpath(__file__)))
print('FILES', os.listdir())

test_files = []
for path, subdirs, files in os.walk(r'tests'):
    test_files.append((os.path.join('Lib/site-packages/galerie', path), glob.glob(os.path.join(path, '*.*'))))


setup(
    name='galerie',
    version='0.0',
    license='MIT',
    packages=['galerie'],
    url = 'https://github.com/GillesArcas/galerie',
    author = 'Gilles Arcas',
    author_email = 'gilles.arcas@gmail.com',
    entry_points = {
        'console_scripts': ['galerie=galerie.galerie:main'],
    },
    zip_safe=False,
    include_package_data=True,
    data_files=[
       ('Lib/site-packages/galerie', ['README.md', 'LICENSE']),
       ('Lib/site-packages/galerie', ['galerie/favicon.ico']),
       ('Lib/site-packages/galerie/photobox', glob.glob('photobox/*.*')),
    ] + test_files,
    install_requires = [
        'clipboard',
        'pillow',
        'lxml',
        'colorama',
        'markdown'
    ]
)
