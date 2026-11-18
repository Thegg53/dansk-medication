import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from otc_parser import atc_to_disease, main, parse_csv, parse_workbook


def workbook(path: Path) -> None:
    files = {
        "xl/workbook.xml": """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="OTC" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels": """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>""",
        "xl/worksheets/sheet1.xml": """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
          <row><c r="A1" t="inlineStr"><is><t>Indikation</t></is></c><c r="B1" t="inlineStr"><is><t>Lægemiddel</t></is></c></row>
          <row><c r="A2" t="inlineStr"><is><t>Hovedpine</t></is></c><c r="B2" t="inlineStr"><is><t>Produkt A</t></is></c></row>
          <row><c r="B3" t="inlineStr"><is><t>Produkt B</t></is></c></row>
          <row><c r="A4" t="inlineStr"><is><t>Forkølelse</t></is></c><c r="B4" t="inlineStr"><is><t>Produkt A</t></is></c></row>
        </sheetData></worksheet>""",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class OtcParserTests(unittest.TestCase):
    def test_groups_medications_and_fills_merged_disease_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "otc.xlsx"
            workbook(path)
            self.assertEqual(
                parse_workbook(path, "OTC"),
                {
                    "Hovedpine": ["Produkt A", "Produkt B"],
                    "Forkølelse": ["Produkt A"],
                },
            )

    def test_cli_writes_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "otc.xlsx"
            target = Path(directory) / "index.json"
            workbook(source)
            with patch("otc_parser.download_workbook", return_value=source):
                self.assertEqual(main(["-o", str(target)]), 0)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["Hovedpine"], ["Produkt A", "Produkt B"])

    def test_atc_codes_become_disease_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "otc.xlsx"
            files = {
                "xl/workbook.xml": """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="OTC" sheetId="1" r:id="rId1"/></sheets></workbook>""",
                "xl/_rels/workbook.xml.rels": """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>""",
                "xl/worksheets/sheet1.xml": """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
                  <row><c r="A1" t="inlineStr"><is><t>ATC-Kode</t></is></c><c r="B1" t="inlineStr"><is><t>Lægemiddel</t></is></c></row>
                  <row><c r="A2" t="inlineStr"><is><t>N02BE01</t></is></c><c r="B2" t="inlineStr"><is><t>Paracetamol</t></is></c></row>
                  <row><c r="B3" t="inlineStr"><is><t>Ibuprofen</t></is></c></row>
                </sheetData></worksheet>""",
            }
            with zipfile.ZipFile(path, "w") as archive:
                for name, content in files.items():
                    archive.writestr(name, content)
            self.assertEqual(parse_workbook(path), {"pain and headache": ["Paracetamol", "Ibuprofen"]})
            self.assertEqual(atc_to_disease("ZZZ01"), "ATC:ZZZ01")

    def test_csv_export_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "otc.csv"
            path.write_text("ATC-Kode;Lægemiddel\nR06A;Cetirizin\n", encoding="utf-8")
            self.assertEqual(parse_csv(path), {"allergy": ["Cetirizin"]})

    def test_web_output_contains_availability_metadata_and_audit_log(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "otc.xlsx"
            target = Path(directory) / "web.json"
            log = Path(directory) / "changes.diff"
            workbook(source)
            with patch("otc_parser.download_workbook", return_value=source):
                self.assertEqual(
                    main(["--web-output", "--availability", "non-pharmacy",
                          "--log", str(log), "-o", str(target)]),
                    0,
                )
            web_data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(web_data["metadata"]["availability"], "non-pharmacy")
            self.assertEqual(web_data["diseases"]["Hovedpine"], ["Produkt A", "Produkt B"])
            self.assertIn("--- previous", log.read_text(encoding="utf-8"))

    def test_cli_generates_standalone_html(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "otc.xlsx"
            html = Path(directory) / "index.html"
            workbook(source)
            with patch("otc_parser.download_workbook", return_value=source):
                self.assertEqual(main(["--web-output", "--html", str(html)]), 0)
            content = html.read_text(encoding="utf-8")
            self.assertIn("const data=", content)
            self.assertIn("Hovedpine", content)


if __name__ == "__main__":
    unittest.main()
