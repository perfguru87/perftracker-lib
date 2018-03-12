# perftracker-client
A client library for the [perftracker](https://github.com/perfguru87/perftracker)

# usage

Simulate a 'website' suite run and upload results:
```
python3.6 ./examples/suite_website.py -v --pt-title="Website suite run" --pt-url http://perftracker.localdomain:9000
```

Use code like `examples/populate.sh` to mass populate perftracker with fake data
