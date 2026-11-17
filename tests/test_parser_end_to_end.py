import json
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "index.html"
SCRIPT = ROOT / "scripts" / "actualizar.py"
FIXTURE = ROOT / "tests" / "fixtures" / "parser_equivalence.xml"
SPEC = importlib.util.spec_from_file_location("actualizar_e2e", SCRIPT)
actualizar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actualizar)


def js_function(source, start, end):
    first = source.index(start)
    return source[first:source.index(end, first)]


class ParserEndToEndEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js no está disponible; CI debe instalarlo")
        html = HTML.read_text(encoding="utf-8")
        parser_functions = js_function(html, "function normalizeCity(city)", "function docs(")
        cls.js_harness = """
const {DOMParser}=require("@xmldom/xmldom");
global.DOMParser=DOMParser;
const fs=require("fs");
var NU={ES617:"Málaga"},PN={malaga:"Málaga"};
var PC={"Málaga":[36.8,-4.6]};
var TW={fuengirola:[36.540,-4.625],marbella:[36.510,-4.886]};
var NO_AND={madrid:1,barcelona:1,valencia:1,bilbao:1,zaragoza:1,murcia:1};
var ES={PRE:"Anuncio previo",PUB:"En plazo",EV:"En evaluación",ADJ:"Adjudicada",RES:"Resuelta",ANUL:"Anulada"};
function nm(s){return (s||"").normalize("NFD").replace(/[\\u0300-\\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim()}
function srcOf(o){o=nm(o);return o.indexOf("ayuntamiento")>=0?"Ayuntamiento":(o.indexOf("junta de andalucia")>=0||o.indexOf("consejeria")>=0||o.indexOf("servicio andaluz")>=0||(o.indexOf("agencia")>=0&&o.indexOf("andaluc")>=0))?"Junta de Andalucía":"PLACSP"}
function g(e,n){var out=[];function walk(x){for(var k=x&&x.firstChild;k;k=k.nextSibling){if(k.nodeType===1){if(k.localName===n)out.push(k);walk(k)}}}walk(e);return out}
function tx(e,n){var x=e&&g(e,n)[0];return x?(x.textContent||"").trim():""}
""" + parser_functions + """
const xml=fs.readFileSync(process.argv[1],"utf8");
const acc={};
parse(xml,acc);
process.stdout.write(JSON.stringify(acc));
"""

    def test_full_records_match_for_reference_xml_feed(self):
        root = ET.fromstring(FIXTURE.read_text(encoding="utf-8"))
        expected = {}
        for entry in root.findall("{*}entry"):
            record = actualizar.parse_entry(entry)
            if record:
                expected[record["k"]] = record
        result = subprocess.run(
            [self.node, "-e", self.js_harness, str(FIXTURE)],
            check=True, capture_output=True, text=True,
        )
        actual = json.loads(result.stdout)

        def normalized(record, python=False):
            value = dict(record)
            docs = []
            for item in value.get("dc", []):
                if python:
                    kind, name, prefix, suffix, *code = item
                    url = actualizar.PX[prefix] + suffix if prefix >= 0 else suffix
                    docs.append([kind, name, url, code[0] if code else ""])
                else:
                    kind, name, prefix, suffix, code = item
                    url = actualizar.PX[prefix] + suffix if prefix >= 0 else suffix
                    docs.append([kind, name, url, code or ""])
            value["dc"] = docs
            return value

        expected = {key: normalized(value, True) for key, value in expected.items()}
        actual = {key: normalized(value, False) for key, value in actual.items()}
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
