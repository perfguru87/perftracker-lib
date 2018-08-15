# perftracker-lib
A client library for the [perftracker](https://github.com/perfguru87/perftracker) and a set of libraries for performance testing

## Supported python version

python2.7

python3.0+

## Building and installing the perftracker-client python package

Installing from pypi.org:

```
pip install perftrackerlib
```

Installing from sources:

```
python3 ./setup.py build
python3 ./setup.py install
```

## Usage Examples

### Python-written Test Suites

Minimalistic test suite:
```
python3 ./examples/pt_suite_example_minimal.py --pt-title="Website suite run" --pt-url http://perftracker.localdomain:9000
```

Simulate a 'website' suite run and upload results:
```
python3 ./examples/pt_suite_example.py -v --pt-title="Website suite run" --pt-project="Default project" --pt-url http://perftracker.localdomain:9000
```

Use code like `examples/pt_suite_example_populate.sh` to mass populate perftracker with fake data

### Control Panel Crawler

Run selenium-based test on a real WordPress Admin panel:
```
python3 ./examples/pt-wp-crawler.py -m -U admin -P pass https://demos1.softaculous.com/WordPress/wp-login.php
```

### Upload pre-generated files with results:

Sometimes you don't want to write a python suite and just grab some files and export results. In this case
you can use the pt-suite-uploader.py tool to parse test/json files (or even launch an external tool) and then
upload results:
```
python3 ./examples/pt-suite-uploader.py -f ./examples/data/sample.txt
python3 ./examples/pt-suite-uploader.py -f -j ./examples/data/sample.json
python3 ./examples/pt-suite-uploader.py -- /bin/echo "tag: my test; score: 2.3;"
...
```

## Contributing a patch

Make a change and test your code before commit:
```
python ./test.py
```

## Release notes

See [http://www.perftracker.org/client/#Release_Notes](http://www.perftracker.org/client/#Release_Notes)
