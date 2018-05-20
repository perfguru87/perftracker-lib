# perftracker-client
A client library for the [perftracker](https://github.com/perfguru87/perftracker)

## Supported python version

python2.7

python3.0+

## Building and installing the perftracker-client python package

```
python3 ./setup.py build
python3 ./setup.py install
```

## Usage Examples

### Test Suites

Simulate a 'website' suite run and upload results:
```
python3 ./examples/pt_suite_example.py -v --pt-title="Website suite run" --pt-url http://perftracker.localdomain:9000
```

Use code like `examples/pt_suite_example_populate.sh` to mass populate perftracker with fake data

### Control Panel Crawler

Run selenium-based test on a real WordPress Admin panel:
```
python3 ./examples/pt-wp-crawler.py -m -U admin -P pass https://demos1.softaculous.com/WordPress/wp-login.php
```

## Contributing a patch

Make a change and test your code before commit:
```
python ./test.py
```
