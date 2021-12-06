import os
import sys
from pathlib import Path
from setuptools import setup, find_packages

if sys.version_info.major != 3:
    raise RuntimeError("This package requires Python 3+")

version = '0.0.3'
pkg_name = 'pylibup'
gitrepo = 'trisongz/pylibup'
root = Path(__file__).parent

requirements = [
    'typer',
    'PyGithub',
    'GitPython',
    'Jinja2',
    'pyyaml',
    'pylogz',
    'requests',
]

args = {
    'packages': find_packages(include = ['pylibup', 'pylibup.*']),
    'install_requires': requirements,
    'long_description': root.joinpath('README.md').read_text(encoding='utf-8'),
    'entry_points': {
        'console_scripts': [
            'pylibup = pylibup.cli:baseCli',
            'pylib = pylibup.cli:baseCli'
        ]
    }
}

setup(
    name=pkg_name,
    version=version,
    url='https://github.com/pylibup',
    license='MIT Style',
    description='Python library Builder with CLI',
    author='Tri Songz',
    author_email='ts@growthengineai.com',
    long_description_content_type="text/markdown",
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development :: Libraries',
    ],
    **args
)