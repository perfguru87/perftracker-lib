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
python3 ./examples/pt_suite_example_fake.py -v --pt-title="Website suite run" --pt-project="Default project" --pt-url http://perftracker.localdomain:9000
```

Use code like `examples/pt_suite_example_populate.sh` to mass populate perftracker with fake data

### Upload pre-generated files with tests results:

Sometimes you don't want to write a python suite and just grab some files and export results. In this case
you can use the pt-suite-uploader.py tool to parse test/json files (or even launch an external tool) and then
upload results:
```
python3 ./tools/pt-suite-uploader.py -f ./examples/data/sample.txt
python3 ./tools/pt-suite-uploader.py -f -j ./examples/data/sample.json
python3 ./tools/pt-suite-uploader.py -- /bin/echo "tag: my test; score: 2.3;"
...
```

### Manage artifacts (i.e. jobs and tests attachments)

The perftracker server supports [artifact management](https://github.com/perfguru87/perftracker)
An artifact is a file which can be stored as blob file and linked to test or job run, for example
it can be test or job log, dump or some test data. Many to many links are allowed

There are three ways how clients can managet the artifacts:
1. perftracker REST API
2. perftrackerlib/client.py - ptArfitact() class
3. the ./tools/pt-artifact-ctl.py tool (see --help)

Short introuduction to pt-artifact-ctl.py:

a) Help

```
pt-artifact-ctl.py --help
Usage: pt-artifact-ctl.py [options] command [command parameters]

Description:
    pt-artifact-ctl.py [options] upload ARTIFACT_FILE_TO_UPLOAD [ARTIFACT_UUID]
    pt-artifact-ctl.py [options] update ARTIFACT_UUID
    pt-artifact-ctl.py [options] delete ARTIFACT_UUID
    pt-artifact-ctl.py [options] info ARTIFACT_UUID
    pt-artifact-ctl.py [options] link ARTIFACT_UUID OBJECT_UUID
    pt-artifact-ctl.py [options] unlink ARTIFACT_UUID OBJECT_UUID
    pt-artifact-ctl.py [options] list [LIMIT]
    pt-artifact-ctl.py [options] download ARTIFACT_UUID ARTIFACT_FILE_TO_SAVE

Options:
  -h, --help                  show this help message and exit
  -v, --verbose               enable verbose mode
  -p PT_SERVER_URL, --pt-server-url=PT_SERVER_URL
                              perftracker url, default http://127.0.0.1:9000
  -d DESCRIPTION, --description=DESCRIPTION
                              artifact description
  -m MIME, --mime=MIME        artifact mime type, default is guessed or
                              'application/octet-stream'
  -f FILENAME, --filename=FILENAME
                              override artifact file name by given name
  -z, --compression           inline decompression on every file view or
                              download
  -i, --inline                inline view in browser (do not download on click)
  -t TTL, --ttl=TTL           time to live (days), default=180, 0 - infinite
```

b) Upload an artifact and link in to the test with uuid = $TEST_UUID

```
./pt-artifact-ctl.py upload ~/my_test.log
./pt-artifact-ctl.py link $ARTIFACT_UUID $TEST_UUID
```

c) Upload an artifact, set infinite time to live, enable dynamic compression and enable inline view in the browser

```
./pt-artifact-ctl.py upload ~/my_test.log -iz -t 0
```

## Contributing a patch

Make a change and test your code before commit:
```
python ./test.py
```

## Release notes

See [http://www.perftracker.org/client/#Release_Notes](http://www.perftracker.org/client/#Release_Notes)
