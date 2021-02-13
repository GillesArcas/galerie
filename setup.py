import glob
from setuptools import setup

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
       ('Lib/site-packages/galerie/photobox', glob.glob('photobox/*.*')),
    ],
    install_requires = [
        'clipboard',
        'pillow',
        'lxml',
        'colorama',
        'markdown'
    ]
)
