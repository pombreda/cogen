#!/usr/bin/python
try:
    import setuptools
except ImportError:

    import ez_setup
    ez_setup.use_setuptools()

from setuptools import setup, find_packages
import sys

from cogen import __version__ as version

setup(
    name='cogen',
    version=version,
    description='''
        Coroutines and asynchronous I/O using enhanced generators 
        from python 2.5, including a enhanced WSGI server.
    ''',
    long_description=file('README.txt').read(),
    author='Maries Ionel Cristian',
    author_email='ionel dot mc at gmail dot com',
    url='http://code.google.com/p/cogen/',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    zip_safe=True,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Operating System :: POSIX :: BSD',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Server',
        'Topic :: System :: Networking',
    ],      
    entry_points={
        'paste.server_factory': [
            'wsgi=cogen.web.wsgi:server_factory',
            'http=cogen.web.wsgi:server_factory',
        ],
        'paste.filter_app_factory': [
            'syncinput=cogen.web.async:SynchronousInputMiddleware',
            'lazysr=cogen.web.async:LazyStartResponseMiddleware'
        ],
        'apydia.themes': [
            'cogen=docgen.theme',
            'cogenwiki=docgen.wikitheme',
        ],
        'apydia.docrenderers': [
            'wiki=docgen.wikirender:WikiTextRenderer'
        ]
    },
    install_requires = \
        (["py-kqueue>=2.0"] if 'bsd' in sys.platform else []) +
        (["py-epoll>=1.2"] if 'linux' in sys.platform else []) +\
        (["py-sendfile>=1.2.2"] if ('linux' in sys.platform) or ('bsd' in sys.platform) else []),
    test_suite='nose.collector',
    tests_require=['nose', 'coverage']
    
)