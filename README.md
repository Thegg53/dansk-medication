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

The parser recognizes Danish and English headers for indication/disease,
ATC code, and medication/product. The agency's export uses ATC codes, so the
standard OTC therapeutic groups are translated to disease categories such as
`pain and headache`, `allergy`, and `cough and cold`. Unknown codes remain
visible as `ATC:<code>`. Blank indication cells inherit the preceding
indication, which handles merged cells used by spreadsheet exports. Duplicate
medicines within an indication are emitted once, in source order.

Run the tests with:

```sh
python3 -m unittest discover -s tests
```
