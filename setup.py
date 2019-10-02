#!/usr/bin/python

from distutils.core import setup

def readme():
    with open('README.md') as f: return f.read()

setup(
    name='Blunt',
    description='Basic video monitoring script for Python',
    url='https://github.com/joel-tuberosa/blunt',
    author='Joel Tuberosa',
    author_email='joel.tuberosa@unige.ch',
    license='GNU',
    scripts=['scripts/activity_monitoring.py',
             'scripts/time_interval_smoothing.py',
             'scripts/video_crop.py',
             'scripts/timestamp.py',
             'scripts/fly_tube.py'],
    py_modules=['blunt'],
    platforms=['any'],
    version='1.0.a1',
    #long_description=readme(),
    classifiers=[
        'Development Status :: 1 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.7',
        'Topic :: Scientific/Engineering :: Bio-Informatics',
        ]
      )
