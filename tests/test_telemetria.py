import importlib.util
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "actualizar.py"
SPEC = importlib.util.spec_from_file_location("actualizar", SCRIPT)
actualizar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actualizar)


def record(key, updated, title="Obra", ficha=None):
    value = {
        "k": key, "id": key, "t": title, "prov": "Málaga",
        "org": "Ayuntamiento de Málaga", "src": "Ayuntamiento",
        "est": "En plazo", "imp": 1500000, "pl": "", "u": "",
        "dc": [], "up": updated, "mun": "Málaga", "la": 36.721,
        "lo": -4.421, "ap": 0,
    }
    if ficha:
        value["ficha"] = ficha
    return value


class TelemetryTests(unittest.TestCase):
    def test_collect_counts_matches_and_only_new_unique_keys(self):
        xml = ET.fromstring(
            "<feed><entry><id>one</id></entry><entry><id>two</id></entry>"
            "<entry><id>three</id></entry></feed>"
        )
        parsed = {
            "one": record("A", "2026-01-01T10:00:00Z"),
            "two": record("A", "2026-01-02T10:00:00Z", "Actualización"),
            "three": record("B", "2025-12-01T10:00:00Z"),
        }
        acc = {}
        with patch.object(actualizar, "parse_entry", side_effect=lambda e: parsed[e.findtext("id")]):
            accepted, unique = actualizar.collect(xml, acc)
        self.assertEqual((accepted, unique), (3, 2))
        self.assertEqual(set(acc), {"A", "B"})
        self.assertEqual(acc["A"]["up"], "2026-01-02T10:00:00Z")

    def test_main_persists_per_feed_telemetry_without_real_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out, checkpoint, status = root / "obras.json", root / "checkpoint.json", root / "status.txt"
            checkpoint.write_text(json.dumps({
                "version": 2, "mode": "initial", "history_cutoff": actualizar.FECHA_MINIMA,
                "feeds": {
                    "perfiles": {"next_url": None, "done": False, "latest_updated": ""},
                    "agregadas": {"next_url": None, "done": False, "latest_updated": ""},
                },
            }), encoding="utf-8")
            feed = b"""<feed xmlns="http://www.w3.org/2005/Atom">
              <entry><id>one</id><updated>2026-03-02T10:00:00Z</updated></entry>
              <entry><id>two</id><updated>2026-03-01T10:00:00Z</updated></entry>
            </feed>"""
            parsed = {
                "one": record("SHARED", "2026-03-02T10:00:00Z"),
                "two": record("SHARED", "2026-03-01T10:00:00Z"),
            }
            args = [
                "actualizar.py", "--pages-per-run", "2",
                "--out", str(out), "--checkpoint", str(checkpoint),
                "--status-file", str(status),
            ]
            with patch.object(actualizar, "FEEDS", {"perfiles": "https://example.test/p", "agregadas": "https://example.test/a"}), \
                 patch.object(actualizar, "fetch", return_value=feed), \
                 patch.object(actualizar, "parse_entry", side_effect=lambda e: parsed[e.findtext("{*}id")]), \
                 patch.object(actualizar.time, "sleep"), patch.object(sys, "argv", args):
                actualizar.main()

            data = json.loads(out.read_text(encoding="utf-8"))
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(status.read_text(encoding="utf-8").strip(), "complete")
            self.assertEqual(len(data["D"]), 1)
            self.assertEqual(data["placsp_progress"]["mode"], "initial")
            self.assertEqual(data["placsp_progress"]["telemetry_scope"], "desde_instrumentacion")
            self.assertTrue(data["placsp_progress"]["telemetry_started_at"])
            for name in ("perfiles", "agregadas"):
                stats = data["placsp_progress"]["feeds"][name]
                self.assertEqual(stats["pages_processed"], 1)
                self.assertEqual(stats["entries_seen"], 2)
                self.assertEqual(stats["entries_matching_filters"], 2)
                self.assertEqual(stats["oldest_updated"], "2026-03-01T10:00:00Z")
                self.assertEqual(stats["newest_updated"], "2026-03-02T10:00:00Z")
            self.assertEqual(
                data["placsp_progress"]["feeds"]["perfiles"]["unique_records_added"], 1
            )
            self.assertEqual(
                data["placsp_progress"]["feeds"]["agregadas"]["unique_records_added"], 0
            )
            self.assertEqual(saved["mode"], "incremental")


class ParserAuditTests(unittest.TestCase):
    def entry(self, estimated, lot_amounts, execution_city="Fuengirola", contracting_city="Madrid", lot_cities=None):
        lot_cities = lot_cities or [execution_city] * len(lot_amounts)
        lots = "".join(
            f"""
            <cac:ProcurementProjectLot>
              <cbc:ID>{index}</cbc:ID>
              <cac:ProcurementProject>
                <cbc:Name>Lote {index}</cbc:Name>
                <cac:BudgetAmount>
                  <cbc:TaxExclusiveAmount>{amount}</cbc:TaxExclusiveAmount>
                </cac:BudgetAmount>
                <cac:RealizedLocation>
                  <cbc:CountrySubentity>Málaga</cbc:CountrySubentity>
                  <cbc:CountrySubentityCode>ES617</cbc:CountrySubentityCode>
                  <cac:Address><cbc:CityName>{lot_city}</cbc:CityName></cac:Address>
                </cac:RealizedLocation>
              </cac:ProcurementProject>
            </cac:ProcurementProjectLot>
            """
            for index, (amount, lot_city) in enumerate(zip(lot_amounts, lot_cities), 1)
        )
        return ET.fromstring(f"""
        <entry xmlns="http://www.w3.org/2005/Atom"
          xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2"
          xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2"
          xmlns:ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2">
          <id>https://contrataciondelestado.es/KEY-1</id>
          <updated>2026-11-17T10:00:00Z</updated>
          <link href="https://example.test/expediente"/>
          <ext:ContractFolderStatus>
            <cbc:ContractFolderID>EXP-1</cbc:ContractFolderID>
            <cbc:ContractFolderStatusCode>PUB</cbc:ContractFolderStatusCode>
            <cac:ProcurementProject>
              <cbc:Name>Obras de rehabilitación</cbc:Name>
              <cbc:TypeCode>3</cbc:TypeCode>
              <cac:BudgetAmount>
                <cbc:EstimatedOverallContractAmount>{estimated}</cbc:EstimatedOverallContractAmount>
                <cbc:TaxExclusiveAmount>900000.25</cbc:TaxExclusiveAmount>
                <cbc:TotalAmount>1089000.30</cbc:TotalAmount>
              </cac:BudgetAmount>
              <cac:RealizedLocation>
                <cbc:CountrySubentity>Málaga</cbc:CountrySubentity>
                <cbc:CountrySubentityCode>ES617</cbc:CountrySubentityCode>
                <cac:Address><cbc:CityName>{execution_city}</cbc:CityName></cac:Address>
              </cac:RealizedLocation>
            </cac:ProcurementProject>
            <cac:LocatedContractingParty>
              <cac:Party>
                <cac:PartyName><cbc:Name>Ayuntamiento de {contracting_city}</cbc:Name></cac:PartyName>
                <cac:PostalAddress><cbc:CityName>{contracting_city}</cbc:CityName></cac:PostalAddress>
              </cac:Party>
            </cac:LocatedContractingParty>
            {lots}
          </ext:ContractFolderStatus>
        </entry>
        """)

    def test_total_expediente_keeps_decimals_and_execution_location(self):
        item = actualizar.parse_entry(self.entry("1250000.75", ["400000.25", "500000.50"], lot_cities=["Fuengirola", "Marbella"]))
        self.assertIsNotNone(item)
        self.assertEqual(item["imp"], 1250000.75)
        self.assertEqual(item["criteria_version"], 2)
        self.assertEqual(item["location_source"], "execution")
        self.assertEqual(item["mun"], "Fuengirola")
        self.assertEqual(item["prov"], "Málaga")
        self.assertEqual(len(item["lotes"]), 2)
        self.assertEqual([lot["id"] for lot in item["lotes"]], ["1", "2"])
        self.assertEqual([lot["mun"] for lot in item["lotes"]], ["Fuengirola", "Marbella"])

    def test_threshold_applies_to_total_expediente_not_each_lot(self):
        item = actualizar.parse_entry(self.entry("0", ["600000.25", "500000.50"]))
        self.assertIsNotNone(item)
        self.assertEqual(item["imp"], 1100000.75)
        self.assertEqual(len(item["lotes"]), 2)

    def test_expediente_at_exact_threshold_is_excluded(self):
        item = actualizar.parse_entry(self.entry("1000000.00", ["600000", "500000"]))
        self.assertIsNone(item)


    def test_missing_execution_city_does_not_infer_city_from_contracting_authority(self):
        item = actualizar.parse_entry(self.entry("1250000", ["1250000"], execution_city="", contracting_city="Marbella"))
        self.assertIsNotNone(item)
        self.assertEqual(item["mun"], "Málaga")
        self.assertEqual((item["la"], item["lo"], item["ap"]), (36.8, -4.6, 1))


if __name__ == "__main__":
    unittest.main()
