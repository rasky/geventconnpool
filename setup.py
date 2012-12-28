from distutils.core import setup
from setuptools import find_packages

setup(name='geventconnpool',
    version = "0.1",
    description = 'TCP connection pool for gevent',
    url="https://github.com/rasky/geventconnpool",
    author="Giovanni Bajo",
    author_email="rasky@develer.com",
    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    install_requires=[
        'gevent >= 0.13'
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: No Input/Output (Daemon)",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 2",
        "Topic :: Software Development",
    ])
