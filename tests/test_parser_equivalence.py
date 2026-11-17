import json
import shutil
import subprocess
import unittest
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "index.html"
SCRIPT = ROOT / "scripts" / "actualizar.py"
SPEC = importlib.util.spec_from_file_location("actualizar_equivalence", SCRIPT)
actualizar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actualizar)


def js_function(source, start, end):
    first = source.index(start)
    last = source.index(end, first)
    return source[first:last]


class ParserEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js no está disponible; CI debe instalarlo")
        html = HTML.read_text(encoding="utf-8")
        functions = "\n".join([
            js_function(html, "function nm(s)", "var NU="),
            js_function(html, "var NO_AND=", "function srcOf("),
            js_function(html, "function money(v)", "function lotesDe("),
            js_function(html, "function importeExpediente(pp,lotes)", "function entryKey("),
            js_function(html, "function entryKey(id)", "function parse(xml,acc)"),
        ])
        cls.js_harness = """
var TW={fuengirola:[36.540,-4.625]};
var PC={"Málaga":[36.8,-4.6]};
function g(e,n){return e && e[n] ? [e[n]] : []}
function tx(e,n){return e && e[n] != null ? String(e[n]) : ""}
""" + functions + """
const input=JSON.parse(process.argv[1]);
const cities=input.cities.map(function(city){
  var r={prov:"Málaga"};loc(r,city);
  return {mun:r.mun,la:r.la,lo:r.lo,ap:r.ap};
});
const amounts=input.amounts.map(money);
const totals=input.totals.map(function(x){
  return importeExpediente({BudgetAmount:x.budget},x.lots);
});
const keys=input.keys.map(entryKey);
process.stdout.write(JSON.stringify({cities:cities,amounts:amounts,totals:totals,keys:keys}));
"""

    def run_js(self, payload):
        result = subprocess.run(
            [self.node, "-e", self.js_harness, json.dumps(payload, ensure_ascii=False)],
            check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout)

    def test_city_normalization_and_fallback_match(self):
        cities = ["Fuengirola (Málaga)", "Madrid", "Lugar sin coordenadas"]
        expected = []
        for city in cities:
            record = {"prov": "Málaga"}
            actualizar.locate(record, city)
            expected.append({
                "mun": record["mun"], "la": record["la"],
                "lo": record["lo"], "ap": record["ap"],
            })
        actual = self.run_js({
            "cities": cities, "amounts": [], "totals": [], "keys": [],
        })["cities"]
        self.assertEqual(actual, expected)

    def test_decimal_rounding_matches_python_half_up(self):
        values = ["1.005", "2.675", "-1.005", "12,34", "invalid", "1e3", "0.004", "0.005"]
        expected = [actualizar.money(value) for value in values]
        actual = self.run_js({
            "cities": [], "amounts": values, "totals": [], "keys": [],
        })["amounts"]
        self.assertEqual(actual, expected)

    def test_total_amount_priority_and_lot_fallback_match(self):
        cases = [
            {
                "budget": {"EstimatedOverallContractAmount": "1250000.755",
                           "TaxExclusiveAmount": "900000.25", "TotalAmount": "1089000.30"},
                "lots": [{"imp": 400000.25}, {"imp": 500000.50}],
            },
            {
                "budget": {"EstimatedOverallContractAmount": "0",
                           "TaxExclusiveAmount": "900000.25", "TotalAmount": "1089000.30"},
                "lots": [{"imp": 600000.25}, {"imp": 500000.50}],
            },
            {
                "budget": {"EstimatedOverallContractAmount": "0",
                           "TaxExclusiveAmount": "900000.25", "TotalAmount": "1089000.30"},
                "lots": [{"imp": 600000.25}, {"imp": 0}],
            },
        ]
        expected = []
        for case in cases:
            budget = case["budget"]
            lots = case["lots"]
            amount = actualizar.money(budget.get("EstimatedOverallContractAmount"))
            if amount <= 0 and lots and all(lot["imp"] > 0 for lot in lots):
                from decimal import Decimal, ROUND_HALF_UP
                amount = float(sum(
                    (Decimal(str(lot["imp"])) for lot in lots), Decimal("0")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if amount <= 0:
                amount = actualizar.money(
                    budget.get("TaxExclusiveAmount") or budget.get("TotalAmount")
                )
            expected.append(amount)
        actual = self.run_js({
            "cities": [], "amounts": [], "totals": cases, "keys": [],
        })["totals"]
        self.assertEqual(actual, expected)

    def test_entry_key_extraction_matches_and_does_not_fallback(self):
        values = [
            "https://contrataciondelestado.es/ABC-123",
            "ABC-123",
            "",
            "https://contrataciondelestado.es/path/",
        ]
        expected = [actualizar.entry_key(value) for value in values]
        actual = self.run_js({
            "cities": [], "amounts": [], "totals": [], "keys": values,
        })["keys"]
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
