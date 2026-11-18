# dansk-medication

Convert the Danish Medicines Agency's non-prescription medicines workbook into
a UTF-8 JSON index of `disease -> medication`.

## Usage

Parse a downloaded workbook:

```sh
python3 otc_parser.py path/to/non-pharmacy-restricted-medicines.xlsx \
  --sheet "Sheet1" -o medications.json
```

With no workbook argument, the parser finds the Excel link on the agency's
[over-the-counter medicines page](https://laegemiddelstyrelsen.dk/en/pharmacies/over-the-counter-medicines/)
and downloads it before producing JSON on standard output:

```sh
python3 otc_parser.py > medications.json
```

For a webpage, generate a self-describing source file:

```sh
python3 otc_parser.py medicines.xlsx --web-output \
  --availability non-pharmacy --log data/update-log.jsonl \
  -o data/medications.json
```

The `metadata` object records the UTC generation time, source checksum,
availability label, and record counts. The `diseases` object retains the
disease-to-medication mapping, so a webpage can filter it directly. Run the
script daily and archive `data/update-log.jsonl` with the generated JSON to
track source changes. Use `pharmacy` when processing a pharmacy-only source.
The current agency workbook is the non-pharmacy-restricted list: it describes
legal eligibility for sale outside pharmacies, not the inventory of a
particular supermarket or 7-Eleven.

The parser recognizes Danish and English headers for indication/disease,
ATC code, and medication/product. The agency's export uses ATC codes, so the
standard OTC therapeutic groups are translated to disease categories such as
`pain and headache`, `allergy`, and `cough and cold`. Unknown codes remain
visible as `ATC:<code>`. Blank indication cells inherit the preceding
indication, which handles merged cells used by spreadsheet exports. Duplicate
medicines within an indication are emitted once, in source order.

ATC codes use the World Health Organization's [Anatomical Therapeutic Chemical
(ATC) classification](https://www.who.int/tools/atc-ddd-toolkit). The labels
are broad, hand-maintained three-character ATC-group categories in
`_ATC_DISEASES`, not clinical diagnoses or medical advice. Unmapped groups
remain visible as `ATC:<code>` until reviewed and added.

Run the tests with:

```sh
python3 -m unittest discover -s tests
```
