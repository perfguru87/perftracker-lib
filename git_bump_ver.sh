#!/bin/sh
VER=`grep "__version__ = " perftrackerlib/__init__.py | cut -d "\"" -f 2`

echo git commit -m \"bump version to $VER\"
echo git tag "v$VER"
echo git push origin --tags
