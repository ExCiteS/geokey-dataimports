#!/usr/bin/env python

"""GeoKey extension for importing data from various formats into GeoKey."""

from os.path import dirname, join
from setuptools import setup, find_packages


def read(file_name):
    with open(join(dirname(__file__), file_name)) as file_object:
        return file_object.read()


name = 'geokey-dataimports'
version = __import__(name.replace('-', '_')).__version__
repository = join('https://github.com/ExCiteS', name)

setup(
    name=name,
    version=version,
    description='Import data from various formats into GeoKey',
    long_description=read('README.rst'),
    url=repository,
    download_url=join(repository, 'tarball', version),
    author='ExCiteS',
    author_email='excites@ucl.ac.uk',
    license='MIT',
    packages=find_packages(exclude=['*.tests', '*.tests.*', 'tests.*']),
    include_package_data=True,
    install_requires=[],
)
