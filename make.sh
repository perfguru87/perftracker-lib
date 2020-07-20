#!/bin/sh
VER=`grep "__version__ = " perftrackerlib/__init__.py | cut -d "\"" -f 2`

echo "\n###### run the following commands manually ######\n"
echo "vim perftrackerlib/__init__.py  # update version"
echo "vim python2-perftracker-lib.spec  # update version"
echo "vim python36-perftracker-lib.spec  # update version"
echo "git commit -m \"bump version to $VER\" perftrackerlib/__init__.py *.spec && git tag \"v$VER\" && git push origin --tags"
echo python3 setup.py sdist bdist_wheel
echo twine upload dist/perftrackerlib-$VER.tar.gz
echo git push
echo
