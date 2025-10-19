from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Stromverbrauch


class StromverbrauchImportTests(TestCase):
    HEADER = ["Zeitstempel", "Zählpunkt", "Obiscode", "Wert (kWh)"]

    @staticmethod
    def _column_letter(index: int) -> str:
        result = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    @staticmethod
    def _excel_serial(value: datetime | date) -> float:
        if isinstance(value, datetime):
            dt_value = value
        else:
            dt_value = datetime.combine(value, datetime.min.time())
        base = datetime(1899, 12, 30)
        delta = dt_value - base
        return delta.days + (delta.seconds / 86400)

    def _build_workbook(self, rows):
        data_rows = [self.HEADER, *rows]

        shared_strings: list[str] = []
        sheet_rows: list[str] = []

        for row_index, row in enumerate(data_rows, start=1):
            cells: list[str] = []
            for col_index, value in enumerate(row, start=1):
                if value is None:
                    continue

                cell_ref = f"{self._column_letter(col_index)}{row_index}"

                if isinstance(value, (datetime, date)):
                    serial = self._excel_serial(value)
                    cell_xml = f'<c r="{cell_ref}"><v>{serial}</v></c>'
                elif isinstance(value, (int, float)):
                    cell_xml = f'<c r="{cell_ref}"><v>{value}</v></c>'
                else:
                    text = str(value)
                    if text not in shared_strings:
                        shared_strings.append(text)
                    index = shared_strings.index(text)
                    cell_xml = f'<c r="{cell_ref}" t="s"><v>{index}</v></c>'

                cells.append(cell_xml)

            sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(sheet_rows)}</sheetData>'
            '</worksheet>'
        )

        shared_xml_entries = ''.join(
            f'<si><t>{value}</t></si>' for value in shared_strings
        )
        shared_strings_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
            f'{shared_xml_entries}'
            '</sst>'
        )

        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        )

        content_types = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )

        rels = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '</Relationships>'
        )

        workbook_rels = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
            'Target="sharedStrings.xml"/>'
            '<Relationship Id="rId3" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
            '</Relationships>'
        )

        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/>'
            '<scheme val="minor"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )

        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", rels)
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            archive.writestr("xl/sharedStrings.xml", shared_strings_xml)
            archive.writestr("xl/styles.xml", styles_xml)
            archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        buffer.seek(0)
        return buffer.getvalue()

    def test_import_creates_new_entries_and_skips_existing(self):
        Stromverbrauch.objects.create(datum=date(2025, 10, 2), verbrauch_kwh=Decimal("6.89400"))

        workbook_bytes = self._build_workbook([
            (datetime(2025, 10, 2), "ATC", "1.8", 6.894),
            (datetime(2025, 10, 3), "ATC", "1.8", 5.321),
        ])
        upload = SimpleUploadedFile(
            "import.xlsx",
            workbook_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(
            reverse("energiedaten:dashboard"),
            {"file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        eintraege = Stromverbrauch.objects.order_by("datum")
        self.assertEqual(eintraege.count(), 2)
        self.assertTrue(eintraege.filter(datum=date(2025, 10, 3)).exists())

    def test_import_ignores_invalid_rows(self):
        workbook_bytes = self._build_workbook([
            ("2.10.2025", "ATC", "1.8", "6,894"),  # gültig (Komma als Dezimaltrenner)
            ("ungültig", "ATC", "1.8", 5.0),  # ungültiges Datum
            (datetime(2025, 10, 4), "ATC", "1.8", None),  # fehlender Wert
        ])
        upload = SimpleUploadedFile(
            "invalid.xlsx",
            workbook_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(
            reverse("energiedaten:dashboard"),
            {"file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Stromverbrauch.objects.count(), 1)
        eintrag = Stromverbrauch.objects.first()
        self.assertEqual(eintrag.datum, date(2025, 10, 2))
        self.assertEqual(eintrag.verbrauch_kwh, Decimal("6.89400"))
