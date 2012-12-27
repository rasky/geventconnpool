from distutils.core import setup
from setuptools import find_packages

setup(name='geventconnpool',
    version = "0.1",
    description = 'TCP connection pool for gevent',
    author="Giovanni Bajo",
    author_email="rasky@develer.com",
    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    install_requires=[
        'gevent >= 0.13'
    ])
