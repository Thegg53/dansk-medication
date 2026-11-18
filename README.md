# Danish OTC medicines

This repository publishes a small webpage that lists over-the-counter
medicines by disease category.

The weekly GitHub Actions job downloads the current file directly from the
[Danish Medicines Agency](https://laegemiddelstyrelsen.dk/en/pharmacies/over-the-counter-medicines/),
creates [`data/medications.json`](data/medications.json), appends a record to
[`data/update-log.jsonl`](data/update-log.jsonl), and deploys
[`index.html`](index.html) to GitHub Pages.

Run the same update locally:

```sh
python3 otc_parser.py --web-output \
  --log data/update-log.jsonl --output data/medications.json
```

The JSON contains `metadata` and `diseases`. The metadata records when the
source was read, its SHA-256 checksum, and the source's availability category.
The current source is the agency's non-pharmacy-restricted list. That means
the product is legally eligible for sale outside pharmacies; it does not
guarantee stock in a specific supermarket or 7-Eleven.

ATC codes come from the WHO [Anatomical Therapeutic Chemical
classification](https://www.who.int/tools/atc-ddd-toolkit). The parser maps
known three-character groups to broad categories and keeps unknown groups as
`ATC:<code>`. These categories support filtering and are not medical diagnoses.

Run tests with:

```sh
python3 -m unittest discover -s tests
```
