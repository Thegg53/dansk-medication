#!/usr/bin/env python3
"""Turn the Danish Medicines Agency's OTC workbook into a disease index."""

from __future__ import annotations

import argparse
import csv
import html
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
import unicodedata
import urllib.request
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

SOURCE_PAGE = "https://laegemiddelstyrelsen.dk/en/pharmacies/over-the-counter-medicines/"
SOURCE_WORKBOOK = "https://laegemiddelstyrelsen.dk/ftp-upload/AktuelleHaandkoebsLaegemidler.xlsx"

_DISEASE_HEADERS = (
    "disease",
    "indication",
    "indikation",
    "sygdom",
    "anvendelse",
    "anvendelsesområde",
    "therapeutic area",
    "terapeutisk område",
)
_MEDICATION_HEADERS = (
    "medication",
    "medicine",
    "medicin",
    "lægemiddel",
    "produktnavn",
    "handelsnavn",
    "product name",
    "product",
)
_ATC_HEADERS = ("atc code", "atc-kode", "atc", "atc code")
_ATC_DISEASES = {
    "A02": "acid-related disorders",
    "A06": "constipation",
    "A07": "intestinal infections",
    "A11": "vitamin deficiency",
    "D01": "fungal skin infections",
    "D06": "skin infections",
    "G04": "urinary tract disorders",
    "M01": "pain and inflammation",
    "N02": "pain and headache",
    "N05": "sleep and anxiety disorders",
    "R01": "nasal congestion",
    "R02": "sore throat",
    "R03": "asthma and breathing disorders",
    "R05": "cough and cold",
    "R06": "allergy",
    "S01": "eye disorders",
}
_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _text(value: object) -> str:
    value = "" if value is None else str(value)
    return " ".join(value.replace("\xa0", " ").split()).strip()


def _header_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _column_index(headers: list[str], candidates: Iterable[str]) -> int:
    normalized = [_header_key(header) for header in headers]
    choices = [_header_key(candidate) for candidate in candidates]
    for choice in choices:
        if choice in normalized:
            return normalized.index(choice)
    for choice in choices:
        for index, header in enumerate(normalized):
            if choice and choice in header:
                return index
    raise ValueError(
        "Workbook must contain an indication/disease column and a medication/product column"
    )


def _column_number(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    if not letters:
        raise ValueError(f"Invalid spreadsheet cell reference: {reference}")
    number = 0
    for char in letters.group():
        number = number * 26 + ord(char) - ord("A") + 1
    return number - 1


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        _text("".join(node.itertext()))
        for node in root.findall("main:si", _NS)
    ]


def _sheet_rows(book: zipfile.ZipFile, sheet_name: str | None = None) -> list[list[str]]:
    workbook = ElementTree.fromstring(book.read("xl/workbook.xml"))
    sheets = workbook.find("main:sheets", _NS)
    if sheets is None:
        raise ValueError("Workbook contains no worksheets")
    selected = next(
        (
            sheet
            for sheet in sheets
            if sheet_name is None or sheet.attrib.get("name") == sheet_name
        ),
        None,
    )
    if selected is None:
        raise ValueError(f"Worksheet not found: {sheet_name}")
    relationship_id = selected.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
    relationships = ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    relationship = next(
        item for item in relationships if item.attrib.get("Id") == relationship_id
    )
    target = relationship.attrib["Target"].lstrip("/")
    if not target.startswith("xl/"):
        target = f"xl/{target}"
    root = ElementTree.fromstring(book.read(target))
    strings = _shared_strings(book)
    rows: list[list[str]] = []
    for row in root.findall(".//main:sheetData/main:row", _NS):
        cells: dict[int, str] = {}
        for cell in row.findall("main:c", _NS):
            index = _column_number(cell.attrib.get("r", "A1"))
            value = cell.find("main:v", _NS)
            inline = cell.find("main:is", _NS)
            if inline is not None:
                content = _text("".join(inline.itertext()))
            elif value is None:
                content = ""
            else:
                content = value.text or ""
                if cell.attrib.get("t") == "s":
                    content = strings[int(content)]
            cells[index] = _text(content)
        if cells:
            rows.append([cells.get(index, "") for index in range(max(cells) + 1)])
    return rows


def _index_rows(
    rows: list[list[str]], headers: list[str]
) -> OrderedDict[str, list[str]]:
    try:
        disease_index = _column_index(headers, _DISEASE_HEADERS)
        atc_index = None
    except ValueError:
        disease_index = None
        atc_index = _column_index(headers, _ATC_HEADERS)
    medication_index = _column_index(headers, _MEDICATION_HEADERS)
    result: OrderedDict[str, list[str]] = OrderedDict()
    previous_disease = ""
    previous_atc = ""
    for row in rows:
        row += [""] * (max(medication_index, disease_index or 0, atc_index or 0) + 1 - len(row))
        if disease_index is not None:
            disease = _text(row[disease_index]) or previous_disease
        else:
            atc = _text(row[atc_index]) or previous_atc
            disease = atc_to_disease(atc) if atc else ""
        medication = _text(row[medication_index])
        if disease:
            previous_disease = disease
        if disease_index is None and atc:
            previous_atc = atc
        if not disease or not medication:
            continue
        medications = result.setdefault(disease, [])
        if medication not in medications:
            medications.append(medication)
    return result


def atc_to_disease(code: str) -> str:
    """Translate an ATC code to the broad condition category it represents."""
    code = _text(code).upper()
    prefix = code[:3]
    return _ATC_DISEASES.get(prefix, f"ATC:{code}") if code else ""


def parse_workbook(path: str | Path, sheet_name: str | None = None) -> OrderedDict[str, list[str]]:
    """Read an OTC .xlsx workbook and return ``disease -> medications``.

    The agency's current export has ATC codes rather than indications, so ATC
    therapeutic groups are used when no explicit disease column is present.
    """
    with zipfile.ZipFile(path) as book:
        rows = _sheet_rows(book, sheet_name)
    rows = [row for row in rows if any(row)]
    if not rows:
        return OrderedDict()
    return _index_rows(rows[1:], rows[0])


def parse_csv(path: str | Path) -> OrderedDict[str, list[str]]:
    """Read the CSV equivalent published by the agency."""
    raw = Path(path).read_bytes()
    content = raw.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=";,	")
    except csv.Error:
        dialect = csv.excel
    rows = [[_text(value) for value in row] for row in csv.reader(content.splitlines(), dialect)]
    rows = [row for row in rows if any(row)]
    return _index_rows(rows[1:], rows[0]) if rows else OrderedDict()


def discover_workbook_url(page_url: str = SOURCE_PAGE) -> str:
    """Find the non-pharmacy-restricted medicines workbook linked from the source page."""
    with urllib.request.urlopen(page_url) as response:
        page = response.read().decode("utf-8", errors="replace")
    links = re.findall(r"""href\s*=\s*["']([^"']+\.(?:xlsx?|XLSX?)(?:\?[^"']*)?)["']""", page)
    if not links:
        raise ValueError("No Excel workbook link was found on the source page")
    for link in links:
        if "non-pharmacy" in html.unescape(link).lower() or "otc" in link.lower():
            return urllib.request.urljoin(page_url, html.unescape(link))
    return urllib.request.urljoin(page_url, html.unescape(links[0]))


def download_workbook(page_url: str = SOURCE_PAGE) -> Path:
    """Download the linked workbook to a temporary file and return its path."""
    try:
        workbook_url = discover_workbook_url(page_url)
    except ValueError:
        workbook_url = SOURCE_WORKBOOK
    target = Path("/tmp") / "dansk-medication-otc.xlsx"
    urllib.request.urlretrieve(workbook_url, target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", help="Worksheet name (defaults to the first worksheet)")
    parser.add_argument("--source-page", default=SOURCE_PAGE, help="Page containing the workbook link")
    parser.add_argument(
        "--availability",
        choices=("non-pharmacy", "pharmacy", "unknown"),
        default="non-pharmacy",
        help="Availability represented by this source file",
    )
    parser.add_argument(
        "--web-output",
        action="store_true",
        help="Wrap the mapping with metadata for a webpage data source",
    )
    parser.add_argument(
        "--log",
        type=Path,
        help="Append a JSON audit record for this generation run",
    )
    parser.add_argument("-o", "--output", type=Path, help="Write JSON to this file")
    args = parser.parse_args(argv)
    try:
        workbook = download_workbook(args.source_page)
        index = parse_csv(workbook) if workbook.suffix.lower() == ".csv" else parse_workbook(workbook, args.sheet)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    generated_at = datetime.now(timezone.utc).isoformat()
    source = SOURCE_WORKBOOK
    metadata = {
        "generated_at": generated_at,
        "source": source,
        "availability": args.availability,
        "disease_count": len(index),
        "medication_count": sum(len(items) for items in index.values()),
    }
    metadata["source_sha256"] = hashlib.sha256(workbook.read_bytes()).hexdigest()
    if args.web_output:
        output_data = {"metadata": metadata, "diseases": index}
    else:
        output_data = index
    output = json.dumps(output_data, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    if args.log:
        with args.log.open("a", encoding="utf-8") as log:
            log.write(json.dumps(metadata, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
