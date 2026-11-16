#!/usr/bin/env python3
"""
Actualiza data/obras.json con licitaciones de OBRA en Andalucía publicadas en PLACSP.
Conserva expedientes cuyo último anuncio publicado en PLACSP sea desde 2024-01-01.

La especificación oficial de PLACSP establece que:
- las entradas se ordenan por <updated>, de más recientes a más antiguas;
- <updated> corresponde a la publicación del último anuncio del expediente;
- las páginas se enlazan mediante rel="next".

Por ello, el corte histórico se hace por <updated>, NO por un supuesto
< published > ni por la fecha del nombre de la URL de la página.

Uso:
  python scripts/actualizar.py --pages-per-run 12
"""
import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "obras.json"
CHECKPOINT_DEFAULT = DATA.parent / "placsp_checkpoint.json"
STATUS_DEFAULT = DATA.parent / "placsp_status.txt"

FEEDS = {
    "perfiles": "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom",
    "agregadas": "https://contrataciondelestado.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom",
}
UA = "LICITAPUB/1.0 (actualizacion de datos abiertos)"
IMPORTE_MINIMO = 1_000_000
FECHA_MINIMA = "2024-01-01"

NUTS = {
    "ES611": "Almería", "ES612": "Cádiz", "ES613": "Córdoba",
    "ES614": "Granada", "ES615": "Huelva", "ES616": "Jaén",
    "ES617": "Málaga", "ES618": "Sevilla",
}
ESTADOS = {
    "PRE": "Anuncio previo", "PUB": "En plazo", "EV": "En evaluación",
    "ADJ": "Adjudicada", "RES": "Resuelta", "ANUL": "Anulada",
}
PX = [
    "https://contrataciondelestado.es/FileSystem/servlet/GetDocumentByIdServlet?cifrado=QUC1GjXXSiLkydRHJBmbpw%3D%3D&DocumentIdParam=",
    "https://contrataciondelestado.es/wps/wcm/connect/PLACE_es/Site/area/docAccCmpnt?srv=cmpnt&cmpntname=GetDocumentsById&source=library&DocumentIdParam=",
]
DOCTAGS = {
    "LegalDocumentReference": "L", "TechnicalDocumentReference": "T",
    "AdditionalDocumentReference": "A", "GeneralDocument": "G",
}
PC = {
    "Almería": (37.0, -2.3), "Cádiz": (36.5, -5.9),
    "Córdoba": (37.9, -4.8), "Granada": (37.3, -3.4),
    "Huelva": (37.5, -6.7), "Jaén": (37.8, -3.5),
    "Málaga": (36.8, -4.6), "Sevilla": (37.4, -5.6),
}
NO_AND = {"madrid", "barcelona", "valencia", "bilbao", "zaragoza", "murcia"}

# Coordenadas municipales utilizadas por el mapa del radar.
TOWNS = """Málaga:36.721,-4.421;Marbella:36.510,-4.886;Estepona:36.427,-5.146;Fuengirola:36.540,-4.625;Torremolinos:36.620,-4.500;Benalmádena:36.595,-4.516;Mijas:36.596,-4.637;Vélez-Málaga:36.775,-4.100;Ronda:36.742,-5.167;Antequera:37.018,-4.560;Nerja:36.746,-3.875;Coín:36.659,-4.756;Alhaurín de la Torre:36.665,-4.562;Alhaurín el Grande:36.642,-4.686;Manilva:36.376,-5.250;Casares:36.445,-5.275;Benahavís:36.523,-5.045;Rincón de la Victoria:36.717,-4.276;Torrox:36.757,-3.951;Cártama:36.711,-4.632;Álora:36.829,-4.700;Ojén:36.563,-4.855;Cádiz:36.527,-6.289;Jerez de la Frontera:36.686,-6.137;Algeciras:36.133,-5.455;La Línea de la Concepción:36.168,-5.348;San Roque:36.210,-5.384;Chiclana de la Frontera:36.419,-6.147;El Puerto de Santa María:36.594,-6.233;San Fernando:36.464,-6.198;Sanlúcar de Barrameda:36.778,-6.352;Barbate:36.193,-5.926;Tarifa:36.014,-5.603;Los Barrios:36.185,-5.490;Conil de la Frontera:36.277,-6.087;Rota:36.622,-6.362;Arcos de la Frontera:36.751,-5.810;Vejer de la Frontera:36.254,-5.966;Puerto Real:36.528,-6.192;Almería:36.834,-2.463;Roquetas de Mar:36.764,-2.614;El Ejido:36.776,-2.815;Níjar:36.965,-2.215;Vera:37.245,-1.862;Adra:36.748,-3.022;Córdoba:37.888,-4.779;Lucena:37.409,-4.485;Puente Genil:37.389,-4.769;Montilla:37.587,-4.639;Priego de Córdoba:37.438,-4.196;Granada:37.177,-3.599;Motril:36.745,-3.518;Almuñécar:36.734,-3.690;Baza:37.490,-2.771;Guadix:37.299,-3.140;Loja:37.168,-4.150;Huelva:37.261,-6.945;Lepe:37.254,-7.205;Isla Cristina:37.199,-7.317;Ayamonte:37.212,-7.403;Almonte:37.264,-6.516;Moguer:37.275,-6.838;Jaén:37.779,-3.785;Linares:38.095,-3.636;Andújar:38.039,-4.051;Úbeda:38.013,-3.371;Martos:37.721,-3.969;Sevilla:37.389,-5.984;Dos Hermanas:37.283,-5.921;Alcalá de Guadaíra:37.337,-5.841;Utrera:37.185,-5.781;Écija:37.542,-5.083;Mairena del Aljarafe:37.349,-6.062;Carmona:37.471,-5.643;Morón de la Frontera:37.122,-5.456;Lebrija:36.921,-6.075;Osuna:37.236,-5.103;Atarfe:37.222,-3.686;Tomares:37.372,-6.048;Mairena del Alcor:37.373,-5.746;Espartinas:37.386,-6.117;Bornos:36.810,-5.743;Vegas del Genil:37.150,-3.683;Las Gabias:37.136,-3.650;Lora del Río:37.659,-5.527;Cabra:37.472,-4.441;Albolote:37.233,-3.653;Bonares:37.331,-6.690;Punta Umbría:37.185,-6.968;Hornachuelos:37.846,-5.231;Vícar:36.833,-2.640;Armilla:37.141,-3.620;San José del Valle:36.600,-5.944;Villanueva de Algaidas:37.178,-4.456;Chauchina:37.176,-3.738;Medina Sidonia:36.459,-5.926;Torreblascopedro:37.992,-3.765;La Algaba:37.464,-6.019;Marchena:37.330,-5.416;Alcalá la Real:37.461,-3.924;Alcalá del Río:37.517,-5.976;Sanlúcar la Mayor:37.387,-6.200;Salobreña:36.745,-3.587;Cuevas del Becerro:36.850,-4.998;Cenes de la Vega:37.139,-3.549;Salteras:37.427,-6.103;Espera:36.855,-5.808;Alcalá del Valle:36.906,-5.152;Trebujena:36.870,-6.180;Chipiona:36.737,-6.440;Baena:37.617,-4.325;Villanueva del Rosario:36.998,-4.351;Grazalema:36.759,-5.368;Marinaleda:37.381,-4.953;Cuevas del Almanzora:37.297,-1.879;Ogíjares:37.130,-3.600;Huércal-Overa:37.390,-1.943;Pulianas:37.236,-3.569;La Roda de Andalucía:37.205,-4.769;San Nicolás del Puerto:37.998,-5.673;Algarrobo:36.765,-4.039;Pozoblanco:38.379,-4.849;Pilas:37.305,-6.306;Villa del Río:37.980,-4.300;Montoro:38.022,-4.384;Guillena:37.543,-6.050;Bailén:38.096,-3.775;Churriana de la Vega:37.139,-3.640;Aracena:37.893,-6.564;La Carlota:37.678,-4.939;El Carpio:37.924,-4.499"""

def nm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

PN = {nm(v): v for v in NUTS.values()}
TW = {}
for item in TOWNS.split(";"):
    name, coords = item.split(":")
    lat, lon = coords.split(",")
    TW[nm(name)] = (float(lat), float(lon))
TK = sorted(TW, key=len, reverse=True)

def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as response:
                return response.read()
        except Exception as exc:
            print(f"  intento {i + 1} fallido: {exc}", file=sys.stderr, flush=True)
            if i + 1 < tries:
                time.sleep(5 * (i + 1))
    raise RuntimeError("No se pudo descargar " + url)

def comp(kind, name, url, code=""):
    item = next(([kind, name, i, url[len(prefix):]]
                 for i, prefix in enumerate(PX) if url.startswith(prefix)),
                [kind, name, -1, url])
    return item + [code] if code else item

def locate(record, city):
    city = re.sub(r"\s*\(.*\)\s*$", "", city or "").strip()
    coords = TW.get(nm(city))
    if not coords:
        haystack = " " + nm(record["org"] + " " + record["t"] + " " + city) + " "
        coords = next((TW[k] for k in TK if " " + k + " " in haystack), None)
    approximate = 0
    if not coords:
        base = PC[record["prov"]]
        digest = hashlib.md5((record["k"] + record["id"]).encode()).digest()
        coords = (base[0] + (digest[0] / 255 - .5) * .3,
                  base[1] + (digest[1] / 255 - .5) * .4)
        approximate = 1
    record["mun"] = record["prov"] if (not city or nm(city) in NO_AND) else city
    record["la"], record["lo"], record["ap"] = round(coords[0], 4), round(coords[1], 4), approximate

def parse_entry(entry):
    contract = entry.find("{*}ContractFolderStatus")
    project = contract.find("{*}ProcurementProject") if contract is not None else None
    if project is None:
        return None
    cpvs = [node.text.strip() for node in project.iterfind(".//{*}ItemClassificationCode") if node.text]
    if not ((project.findtext("{*}TypeCode") or "").strip() == "3" or any(code.startswith("45") for code in cpvs)):
        return None
    nuts = (project.findtext("{*}RealizedLocation/{*}CountrySubentityCode") or "").strip()
    subentity = project.findtext("{*}RealizedLocation/{*}CountrySubentity") or ""
    province = NUTS.get(nuts[:5]) if nuts.startswith("ES61") else PN.get(nm(subentity))
    if not province:
        return None
    key = re.sub(r"^.*/", "", (entry.findtext("{*}id") or "").strip())
    contract_id = (contract.findtext("{*}ContractFolderID") or "").strip()
    if not key or not contract_id:
        return None
    party = contract.find("{*}LocatedContractingParty")
    org = (party.findtext(".//{*}PartyName/{*}Name") or "").strip() if party is not None else ""
    city = (party.findtext(".//{*}CityName") or "").strip() if party is not None else ""
    budget = project.find("{*}BudgetAmount")
    try:
        amount = round(float((budget.findtext("{*}TaxExclusiveAmount") or
                              budget.findtext("{*}EstimatedOverallContractAmount") or "0").strip()))
    except Exception:
        amount = 0
    if amount <= IMPORTE_MINIMO:
        return None
    org_norm = nm(org)
    source = ("Ayuntamiento" if "ayuntamiento" in org_norm else
              "Junta de Andalucía" if ("junta de andalucia" in org_norm or "consejeria" in org_norm
              or "servicio andaluz" in org_norm or ("agencia" in org_norm and "andaluc" in org_norm))
              else "PLACSP")
    link = next((node.get("href", "") for node in entry.findall("{*}link")), "")
    documents, seen = [], set()
    for node in contract:
        tag = DOCTAGS.get(node.tag.split("}")[1])
        url = (node.findtext(".//{*}URI") or "").strip()
        if tag and url and url not in seen:
            seen.add(url)
            if tag == "G":
                documents.append(comp(tag, (node.findtext(".//{*}FileName") or "").strip(), url,
                                      (node.findtext(".//{*}DocumentTypeCode") or "").strip()))
            else:
                documents.append(comp(tag, (node.findtext("{*}ID") or "").strip(), url))
    updated = (entry.findtext("{*}updated") or "").strip()
    record = {
        "k": key, "id": contract_id, "t": (project.findtext("{*}Name") or "").strip(),
        "prov": province, "org": org, "src": source,
        "est": ESTADOS.get((contract.findtext("{*}ContractFolderStatusCode") or "").strip(), "Desconocido"),
        "imp": amount,
        "pl": (contract.findtext("{*}TenderingProcess/{*}TenderSubmissionDeadlinePeriod/{*}EndDate") or "").strip(),
        "u": link, "dc": documents, "up": updated,
    }
    if len(record["t"]) > 240:
        record["t"] = record["t"][:237] + "…"
    locate(record, city)
    return record

def collect(root, acc):
    accepted = 0
    for entry in root.findall("{*}entry"):
        record = parse_entry(entry)
        # PLACSP documenta que <updated> es la fecha del último anuncio y
        # que las entradas se ordenan globalmente de más nuevas a más antiguas.
        if not record or record["up"][:10] < FECHA_MINIMA:
            continue
        accepted += 1
        previous = acc.get(record["k"])
        if previous is None or record["up"] >= previous.get("up", ""):
            if previous and previous.get("ficha") and record["up"] == previous.get("up", ""):
                record["ficha"] = previous["ficha"]
            acc[record["k"]] = record
    return accepted

def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")
    temp.replace(path)

def page_next(root):
    return next((link.get("href") for link in root.findall("{*}link")
                 if link.get("rel") == "next" and link.get("href")), None)

def page_updated(root):
    return max((entry.findtext("{*}updated") or ""
                for entry in root.findall("{*}entry")), default="")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages-per-run", type=int, default=12)
    parser.add_argument("--out", default=str(DATA))
    parser.add_argument("--checkpoint", default=str(CHECKPOINT_DEFAULT))
    parser.add_argument("--status-file", default=str(STATUS_DEFAULT))
    args = parser.parse_args()
    if args.pages_per_run < 1:
        sys.exit("--pages-per-run debe ser mayor que cero")

    out, checkpoint, status_path = Path(args.out), Path(args.checkpoint), Path(args.status_file)
    old = json.loads(out.read_text("utf-8")) if out.exists() else {"D": []}
    # Limpia del conjunto los registros cuyo último anuncio es anterior al corte.
    acc = {
        record["k"]: record for record in old.get("D", [])
        if "k" in record and float(record.get("imp") or 0) > IMPORTE_MINIMO
        and (record.get("up") or "")[:10] >= FECHA_MINIMA
    }

    if checkpoint.exists():
        state = json.loads(checkpoint.read_text("utf-8"))
    else:
        state = {"version": 2, "mode": "initial", "feeds": {}}

    mode = state.get("mode", "initial")
    if mode not in ("initial", "incremental"):
        sys.exit("Modo de checkpoint desconocido; no se sobrescriben los datos")

    # Si cambia el límite histórico, reinicia los cursores de ambos feeds.
    # No borra las fichas válidas ya guardadas; reconstruye desde el primer feed.
    if state.get("history_cutoff") != FECHA_MINIMA:
        state = {
            "version": 2,
            "mode": "initial",
            "history_cutoff": FECHA_MINIMA,
            "feeds": {
                name: {"next_url": None, "done": False, "latest_updated": ""}
                for name in FEEDS
            },
        }
        mode = "initial"

    now = datetime.now(timezone.utc)
    for name in FEEDS:
        state.setdefault("feeds", {}).setdefault(
            name, {"next_url": None, "done": False, "latest_updated": ""}
        )

    # Marca de agua incremental: conserva la fecha más reciente alcanzada
    # durante la reconstrucción histórica completa.
    if mode == "incremental" and "cycle_since" not in state:
        watermarks = [state["feeds"][name].get("latest_updated", "") for name in FEEDS]
        dates = [value[:10] for value in watermarks if value]
        base = min(dates) if dates else (now - timedelta(days=7)).strftime("%Y-%m-%d")
        state["cycle_since"] = (
            datetime.fromisoformat(base) - timedelta(days=3)
        ).strftime("%Y-%m-%d")

    def save(complete=False):
        records = sorted(acc.values(), key=lambda row: row.get("up", ""), reverse=True)
        meta = {
            key: value for key, value in old.items()
            if key not in ("D", "info", "updated", "feed_until", "initial_window_done")
        }
        meta.update({
            "info": f"{len(records)} licitaciones de obra en Andalucía · PLACSP · importe superior a 1.000.000 € · desde {FECHA_MINIMA}",
            "updated": now.strftime("%d/%m/%Y"),
            "feed_until": max((state["feeds"][name].get("latest_updated", "") for name in FEEDS), default=""),
            "initial_window_done": complete or mode == "incremental",
            "px": PX,
            "D": records,
        })
        # Primero datos y después checkpoint: nunca adelantar el cursor si falla la escritura.
        atomic_json(out, meta)
        atomic_json(checkpoint, state)

    budget = args.pages_per_run
    failure = None
    for name, start_url in FEEDS.items():
        feed_state = state["feeds"][name]
        if feed_state.get("done"):
            continue
        while budget > 0:
            url = feed_state.get("next_url") or start_url
            print(f"{mode} / {name}: descargando página, quedan {budget} en este lote", flush=True)
            try:
                root = ET.fromstring(fetch(url))
                accepted = collect(root, acc)
            except Exception as exc:
                failure = f"{name}: {exc}"
                print("ERROR recuperable:", failure, file=sys.stderr, flush=True)
                break

            updated = page_updated(root)
            feed_state["latest_updated"] = max(feed_state.get("latest_updated", ""), updated)
            next_url = page_next(root)

            # Paginación oficial: orden global por updated, descendente.
            # Se termina el feed cuando la fecha más reciente de la página
            # ya es anterior al 01/01/2024 (en ese punto todas son más antiguas).
            older_than_cutoff = bool(updated) and updated[:10] < FECHA_MINIMA
            older_incremental = bool(
                mode == "incremental" and updated and updated[:10] < state["cycle_since"]
            )
            feed_state["done"] = not next_url or older_than_cutoff or older_incremental
            feed_state["next_url"] = None if feed_state["done"] else next_url
            budget -= 1
            save()

            print(f"  entradas válidas incorporadas: {accepted}", flush=True)
            if feed_state["done"]:
                print(f"{name}: feed terminado", flush=True)
                break
            time.sleep(0.5)
        if failure or budget == 0:
            break

    cycle_complete = all(state["feeds"][name].get("done") for name in FEEDS)
    if cycle_complete:
        if mode == "initial":
            state["mode"] = "incremental"
        state.pop("cycle_since", None)
        for feed_state in state["feeds"].values():
            feed_state["done"] = False
            feed_state["next_url"] = None
        save(complete=True)
        status = "complete"
    else:
        save(complete=False)
        status = "pending"

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(status + "\n", "utf-8")
    print(
        f"STATUS={status} licitaciones={len(acc)}"
        + (f" error={failure}" if failure else ""),
        flush=True,
    )

if __name__ == "__main__":
    main()
