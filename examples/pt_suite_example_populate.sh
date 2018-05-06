#!/bin/sh

dir=`dirname ${BASH_SOURCE[0]}`

for suite_ver in 1 2 3
do
	for build in `seq 100 150`
	do
		python3 "$dir/pt_suite_example.py" --pt-title="My web app, 1.0-$suite_ver$build" --pt-version="1.0.$suite_ver"
	done
done
