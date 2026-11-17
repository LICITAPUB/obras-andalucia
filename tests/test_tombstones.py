import unittest
import xml.etree.ElementTree as ET
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("actualizar_tombstones", ROOT / "scripts" / "actualizar.py")
actualizar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actualizar)


class TombstoneTests(unittest.TestCase):
    def setUp(self):
        self.record = {"k": "123", "up": "2026-05-01T10:00:00+02:00", "est": "En evaluación"}
        self.acc = {"123": self.record}

    def deleted(self, when, kind):
        kind_xml = f'<at:comment type="{kind}"/>' if kind else ""
        return ET.fromstring(
            f'<at:deleted-entry xmlns:at="http://purl.org/atompub/tombstones/1.0" '
            f'ref="https://contrataciondelestado.es/sindicacion/123" when="{when}">'
            f'{kind_xml}</at:deleted-entry>'
        )

    def test_later_closed_tombstone_is_preserved(self):
        node = self.deleted("2026-05-02T10:00:00+02:00", "CERRADA")
        self.assertTrue(actualizar.apply_deleted_entry(node, self.acc))
        self.assertEqual(self.record["est"], "Cerrada")
        self.assertEqual(self.record["estado_publicado"], "En evaluación")
        self.assertEqual(self.record["tombstone"]["tipo"], "CERRADA")

    def test_later_cancelled_tombstone_is_preserved(self):
        node = self.deleted("2026-05-02T10:00:00+02:00", "ANULADA")
        self.assertTrue(actualizar.apply_deleted_entry(node, self.acc))
        self.assertEqual(self.record["est"], "Anulada")

    def test_older_tombstone_does_not_override_newer_entry(self):
        node = self.deleted("2026-04-30T10:00:00+02:00", "CERRADA")
        self.assertFalse(actualizar.apply_deleted_entry(node, self.acc))
        self.assertEqual(self.record["est"], "En evaluación")

    def test_unknown_tombstone_type_is_not_dropped(self):
        node = self.deleted("2026-05-02T10:00:00+02:00", None)
        self.assertTrue(actualizar.apply_deleted_entry(node, self.acc))
        self.assertEqual(self.record["est"], "Retirada del feed")

    def test_tombstone_comparison_respects_timezone_offsets(self):
        self.record["up"] = "2026-05-02T09:30:00+02:00"
        node = self.deleted("2026-05-02T08:00:00+01:00", "CERRADA")
        self.assertTrue(actualizar.apply_deleted_entry(node, self.acc))
        self.assertEqual(self.record["est"], "Cerrada")


if __name__ == "__main__":
    unittest.main()
