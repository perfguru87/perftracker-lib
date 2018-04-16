# perftracker-client
A client library for the [perftracker](https://github.com/perfguru87/perftracker)

## Supported python version

python2.7

python3.0+

## Building and installing the perftracker-client python package

```
python ./setup.py build
python ./setup.py install
```

## Usage

Simulate a 'website' suite run and upload results:
```
python3.6 ./examples/pt_suite_example.py -v --pt-title="Website suite run" --pt-url http://perftracker.localdomain:9000
```

Use code like `examples/pt_suite_example_populate.sh` to mass populate perftracker with fake data

## Contributing a patch

Make a change and test your code before commit:
```
python ./test.py
```
