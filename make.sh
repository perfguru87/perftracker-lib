#!/bin/sh
VER=`grep "__version__ = " perftrackerlib/__init__.py | cut -d "\"" -f 2`

echo "git commit -m \"bump version to $VER\" perftrackerlib/__init__.py && git tag \"v$VER\" && git push origin --tags"
echo python3 setup.py sdist bdist_wheel
echo twine upload dist/pertrackerlib*.tgz
