#!/usr/bin/env python3
"""
Actualiza data/obras.json con licitaciones de OBRA en Andalucía publicadas en PLACSP
(perfiles del contratante + plataformas agregadas, sin contratos menores).

Solo usa la librería estándar de Python 3.8+. Lo ejecuta GitHub Actions cada día;
también puedes lanzarlo a mano:
  python scripts/actualizar.py                       # descarga lo nuevo desde el feed
  python scripts/actualizar.py --zip mes.zip --no-live   # cargar un ZIP mensual
"""
import argparse, hashlib, json, re, sys, time, unicodedata, urllib.request, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "obras.json"
FEEDS = {
    "perfiles": "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom",
    "agregadas": "https://contrataciondelestado.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom",
}
UA = "obras-andalucia-dashboard/1.0 (actualizacion diaria de datos abiertos)"
IMPORTE_MINIMO = 1_000_000
NUTS = {"ES611": "Almería", "ES612": "Cádiz", "ES613": "Córdoba", "ES614": "Granada",
        "ES615": "Huelva", "ES616": "Jaén", "ES617": "Málaga", "ES618": "Sevilla"}
ESTADOS = {"PRE": "Anuncio previo", "PUB": "En plazo", "EV": "En evaluación",
           "ADJ": "Adjudicada", "RES": "Resuelta", "ANUL": "Anulada"}
PX = ["https://contrataciondelestado.es/FileSystem/servlet/GetDocumentByIdServlet?cifrado=QUC1GjXXSiLkydRHJBmbpw%3D%3D&DocumentIdParam=",
      "https://contrataciondelestado.es/wps/wcm/connect/PLACE_es/Site/area/docAccCmpnt?srv=cmpnt&cmpntname=GetDocumentsById&source=library&DocumentIdParam="]
DOCTAGS = {"LegalDocumentReference": "L", "TechnicalDocumentReference": "T",
           "AdditionalDocumentReference": "A", "GeneralDocument": "G"}
PC = {"Almería": (37.0, -2.3), "Cádiz": (36.5, -5.9), "Córdoba": (37.9, -4.8), "Granada": (37.3, -3.4),
      "Huelva": (37.5, -6.7), "Jaén": (37.8, -3.5), "Málaga": (36.8, -4.6), "Sevilla": (37.4, -5.6)}
NO_AND = {"madrid", "barcelona", "valencia", "bilbao", "zaragoza", "murcia"}
TOWNS = "Málaga:36.721,-4.421;Marbella:36.510,-4.886;Estepona:36.427,-5.146;Fuengirola:36.540,-4.625;Torremolinos:36.620,-4.500;Benalmádena:36.595,-4.516;Mijas:36.596,-4.637;Vélez-Málaga:36.775,-4.100;Ronda:36.742,-5.167;Antequera:37.018,-4.560;Nerja:36.746,-3.875;Coín:36.659,-4.756;Alhaurín de la Torre:36.665,-4.562;Alhaurín el Grande:36.642,-4.686;Manilva:36.376,-5.250;Casares:36.445,-5.275;Benahavís:36.523,-5.045;Rincón de la Victoria:36.717,-4.276;Torrox:36.757,-3.951;Cártama:36.711,-4.632;Álora:36.829,-4.700;Ojén:36.563,-4.855;Cádiz:36.527,-6.289;Jerez de la Frontera:36.686,-6.137;Algeciras:36.133,-5.455;La Línea de la Concepción:36.168,-5.348;San Roque:36.210,-5.384;Chiclana de la Frontera:36.419,-6.147;El Puerto de Santa María:36.594,-6.233;San Fernando:36.464,-6.198;Sanlúcar de Barrameda:36.778,-6.352;Barbate:36.193,-5.926;Tarifa:36.014,-5.603;Los Barrios:36.185,-5.490;Conil de la Frontera:36.277,-6.087;Rota:36.622,-6.362;Arcos de la Frontera:36.751,-5.810;Vejer de la Frontera:36.254,-5.966;Puerto Real:36.528,-6.192;Almería:36.834,-2.463;Roquetas de Mar:36.764,-2.614;El Ejido:36.776,-2.815;Níjar:36.965,-2.215;Vera:37.245,-1.862;Adra:36.748,-3.022;Córdoba:37.888,-4.779;Lucena:37.409,-4.485;Puente Genil:37.389,-4.769;Montilla:37.587,-4.639;Priego de Córdoba:37.438,-4.196;Granada:37.177,-3.599;Motril:36.745,-3.518;Almuñécar:36.734,-3.690;Baza:37.490,-2.771;Guadix:37.299,-3.140;Loja:37.168,-4.150;Huelva:37.261,-6.945;Lepe:37.254,-7.205;Isla Cristina:37.199,-7.317;Ayamonte:37.212,-7.403;Almonte:37.264,-6.516;Moguer:37.275,-6.838;Jaén:37.779,-3.785;Linares:38.095,-3.636;Andújar:38.039,-4.051;Úbeda:38.013,-3.371;Martos:37.721,-3.969;Sevilla:37.389,-5.984;Dos Hermanas:37.283,-5.921;Alcalá de Guadaíra:37.337,-5.841;Utrera:37.185,-5.781;Écija:37.542,-5.083;Mairena del Aljarafe:37.349,-6.062;Carmona:37.471,-5.643;Morón de la Frontera:37.122,-5.456;Lebrija:36.921,-6.075;Osuna:37.236,-5.103;Atarfe:37.222,-3.686;Tomares:37.372,-6.048;Mairena del Alcor:37.373,-5.746;Espartinas:37.386,-6.117;Bornos:36.810,-5.743;Vegas del Genil:37.150,-3.683;Las Gabias:37.136,-3.650;Mairena del Aljarafe:37.349,-6.062;Mairena de Aljarafe:37.349,-6.062;Lora del Río:37.659,-5.527;Cabra:37.472,-4.441;Albolote:37.233,-3.653;Bonares:37.331,-6.690;Punta Umbría:37.185,-6.968;Hornachuelos:37.846,-5.231;Vícar:36.833,-2.640;Armilla:37.141,-3.620;San José del Valle:36.600,-5.944;Villanueva de Algaidas:37.178,-4.456;Chauchina:37.176,-3.738;Medina Sidonia:36.459,-5.926;Torreblascopedro:37.992,-3.765;La Algaba:37.464,-6.019;Marchena:37.330,-5.416;Alcalá la Real:37.461,-3.924;Alcalá del Río:37.517,-5.976;Sanlúcar la Mayor:37.387,-6.200;Salobreña:36.745,-3.587;Cuevas del Becerro:36.850,-4.998;Cenes de la Vega:37.139,-3.549;Salteras:37.427,-6.103;Espera:36.855,-5.808;Alcalá del Valle:36.906,-5.152;Trebujena:36.870,-6.180;Chipiona:36.737,-6.440;Baena:37.617,-4.325;Villanueva del Rosario:36.998,-4.351;Grazalema:36.759,-5.368;Marinaleda:37.381,-4.953;Cuevas del Almanzora:37.297,-1.879;Ogíjares:37.130,-3.600;Huércal-Overa:37.390,-1.943;Pulianas:37.236,-3.569;La Roda de Andalucía:37.205,-4.769;San Nicolás del Puerto:37.998,-5.673;Algarrobo:36.765,-4.039;Pozoblanco:38.379,-4.849;Pilas:37.305,-6.306;Villa del Río:37.980,-4.300;Montoro:38.022,-4.384;Guillena:37.543,-6.050;Bailén:38.096,-3.775;Churriana de la Vega:37.139,-3.640;Aracena:37.893,-6.564;La Carlota:37.678,-4.939;El Carpio:37.924,-4.499"


def nm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


PN = {nm(v): v for v in NUTS.values()}
TW = {}
for _t in TOWNS.split(";"):
    _a, _b = _t.split(":")
    _la, _lo = _b.split(",")
    TW[nm(_a)] = (float(_la), float(_lo))
TK = sorted(TW, key=len, reverse=True)


def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:
            print(f"  intento {i + 1} fallido: {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))
    raise RuntimeError("no se pudo descargar " + url)


def roots_zip(path):
    with zipfile.ZipFile(path) as z:
        for n in sorted(x for x in z.namelist() if x.endswith(".atom")):
            yield ET.fromstring(z.read(n))


def roots_live(url, max_pages, since):
    for i in range(max_pages):
        print(f"  página {i + 1}", file=sys.stderr)
        root = ET.fromstring(fetch(url))
        yield root
        nxt = next((l.get("href") for l in root.findall("{*}link") if l.get("rel") == "next"), None)
        ups = [(e.findtext("{*}updated") or "") for e in root.findall("{*}entry")]
        if not nxt or (ups and max(ups) < since):
            return
        url = nxt
        time.sleep(1)


def comp(t, n, u, code=""):
    """Documento comprimido: [tipo, nombre, índice de prefijo, resto de URL(, código)]."""
    x = next(([t, n, i, u[len(p):]] for i, p in enumerate(PX) if u.startswith(p)), [t, n, -1, u])
    return x + [code] if code else x


def parse_entry(e):
    c = e.find("{*}ContractFolderStatus")
    pp = c.find("{*}ProcurementProject") if c is not None else None
    if pp is None:
        return None
    cpv = [x.text.strip() for x in pp.iterfind(".//{*}ItemClassificationCode") if x.text]
    if not ((pp.findtext("{*}TypeCode") or "").strip() == "3" or any(x.startswith("45") for x in cpv)):
        return None
    nuts = (pp.findtext("{*}RealizedLocation/{*}CountrySubentityCode") or "").strip()
    sub = pp.findtext("{*}RealizedLocation/{*}CountrySubentity") or ""
    prov = NUTS.get(nuts[:5]) if nuts.startswith("ES61") else PN.get(nm(sub))
    if not prov:
        return None
    key = re.sub(r"^.*/", "", (e.findtext("{*}id") or "").strip())
    cid = (c.findtext("{*}ContractFolderID") or "").strip()
    if not key or not cid:
        return None
    party = c.find("{*}LocatedContractingParty")
    org = (party.findtext(".//{*}PartyName/{*}Name") or "").strip() if party is not None else ""
    city = (party.findtext(".//{*}CityName") or "").strip() if party is not None else ""
    ba = pp.find("{*}BudgetAmount")
    try:
        imp = round(float((ba.findtext("{*}TaxExclusiveAmount") or ba.findtext("{*}EstimatedOverallContractAmount") or "0").strip()))
    except Exception:
        imp = 0
    # Solo obras con importe estimado sin IVA superior a 1.000.000 €.
    if imp <= IMPORTE_MINIMO:
        return None
    o = nm(org)
    src = ("Ayuntamiento" if "ayuntamiento" in o else
           "Junta de Andalucía" if ("junta de andalucia" in o or "consejeria" in o or "servicio andaluz" in o
                                    or ("agencia" in o and "andaluc" in o)) else "PLACSP")
    link = next((l.get("href", "") for l in e.findall("{*}link")), "")
    seen, dc = set(), []
    for k in c:
        t = DOCTAGS.get(k.tag.split("}")[1])
        u = (k.findtext(".//{*}URI") or "").strip()
        if t and u and u not in seen:
            seen.add(u)
            if t == "G":  # documentos generales: traen nombre de fichero y código de tipo
                dc.append(comp(t, (k.findtext(".//{*}FileName") or "").strip(), u,
                               (k.findtext(".//{*}DocumentTypeCode") or "").strip()))
            else:
                dc.append(comp(t, (k.findtext("{*}ID") or "").strip(), u))
    r = {"k": key, "id": cid, "t": (pp.findtext("{*}Name") or "").strip(), "prov": prov, "org": org,
         "src": src, "est": ESTADOS.get((c.findtext("{*}ContractFolderStatusCode") or "").strip(), "Desconocido"),
         "imp": imp, "pl": (c.findtext("{*}TenderingProcess/{*}TenderSubmissionDeadlinePeriod/{*}EndDate") or "").strip(),
         "u": link, "dc": dc, "up": (e.findtext("{*}updated") or "").strip()}
    if len(r["t"]) > 240:
        r["t"] = r["t"][:237] + "…"
    locate(r, city)
    return r


def locate(r, city):
    city = re.sub(r"\s*\(.*\)\s*$", "", city or "").strip()
    c = TW.get(nm(city))
    if not c:
        h = " " + nm(r["org"] + " " + r["t"] + " " + city) + " "
        c = next((TW[k] for k in TK if " " + k + " " in h), None)
    ap = 0
    if not c:
        q = PC[r["prov"]]
        h = hashlib.md5((r["k"] + r["id"]).encode()).digest()
        c = (q[0] + (h[0] / 255 - .5) * .3, q[1] + (h[1] / 255 - .5) * .4)
        ap = 1
    r["mun"] = r["prov"] if (not city or nm(city) in NO_AND) else city
    r["la"], r["lo"], r["ap"] = round(c[0], 4), round(c[1], 4), ap


def collect(roots, acc):
    n = 0
    for root in roots:
        for e in root.findall("{*}entry"):
            r = parse_entry(e)
            if r:
                n += 1
                old = acc.get(r["k"])
                if old is None or r["up"] >= old.get("up", ""):
                    # Mantener el enriquecimiento si el anuncio no ha cambiado.
                    # Si PLACSP publica una actualización nueva, se vuelve a analizar.
                    if old and old.get("ficha") and r["up"] == old.get("up", ""):
                        r["ficha"] = old["ficha"]
                    acc[r["k"]] = r
    return n



def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")
    temp.replace(path)


def page_next(root):
    return next((l.get("href") for l in root.findall("{*}link")
                 if l.get("rel") == "next" and l.get("href")), None)


def page_updated(root):
    return max((e.findtext("{*}updated") or "" for e in root.findall("{*}entry")), default="")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages-per-run", type=int, default=12)
    ap.add_argument("--out", default=str(DATA))
    ap.add_argument("--checkpoint", default=str(DATA.parent / "placsp_checkpoint.json"))
    ap.add_argument("--status-file", default=str(DATA.parent / "placsp_status.txt"))
    a = ap.parse_args()
    if a.pages_per_run < 1:
        sys.exit("--pages-per-run debe ser mayor que cero")
    out, cp, status_path = Path(a.out), Path(a.checkpoint), Path(a.status_file)
    old = json.loads(out.read_text("utf-8")) if out.exists() else {"D": []}
    acc = {r["k"]: r for r in old.get("D", []) if "k" in r and float(r.get("imp") or 0) > IMPORTE_MINIMO}
    if cp.exists():
        state = json.loads(cp.read_text("utf-8"))
    else:
        state = {"version": 2, "mode": "initial", "feeds": {}}
    mode = state.get("mode", "initial")
    if mode not in ("initial", "incremental"):
        sys.exit("Modo de checkpoint desconocido; no se sobrescriben los datos")
    now = datetime.now(timezone.utc)
    for name in FEEDS:
        state.setdefault("feeds", {}).setdefault(name, {
            "next_url": None, "done": False, "latest_updated": ""
        })

    # La marca de agua es por feed y solo se actualiza al cerrar el ciclo entero.
    if mode == "incremental" and "cycle_since" not in state:
        watermarks = [state["feeds"][n].get("latest_updated", "") for n in FEEDS]
        dates = [d[:10] for d in watermarks if d]
        base = min(dates) if dates else (now - timedelta(days=7)).strftime("%Y-%m-%d")
        state["cycle_since"] = (datetime.fromisoformat(base) - timedelta(days=3)).strftime("%Y-%m-%d")

    def save(complete=False):
        D = sorted(acc.values(), key=lambda r: r.get("up", ""), reverse=True)
        meta = {k: v for k, v in old.items() if k not in ("D", "info", "updated", "feed_until", "initial_window_done")}
        meta.update({
            "info": f"{len(D)} licitaciones de obra en Andalucía · PLACSP · importe superior a 1.000.000 €",
            "updated": now.strftime("%d/%m/%Y"),
            "feed_until": max((state["feeds"][n].get("latest_updated", "") for n in FEEDS), default=""),
            "initial_window_done": complete or mode == "incremental",
            "px": PX, "D": D,
        })
        # Se guardan primero los datos, luego el cursor: no se adelanta el cursor
        # si la escritura de los datos falla.
        atomic_json(out, meta)
        atomic_json(cp, state)

    budget = a.pages_per_run
    failure = None
    for name, start_url in FEEDS.items():
        fs = state["feeds"][name]
        if fs.get("done"):
            continue
        while budget > 0:
            url = fs.get("next_url") or start_url
            print(f"{mode} / {name}: descargando página, quedan {budget} en este lote", flush=True)
            try:
                root = ET.fromstring(fetch(url))
                collect([root], acc)
            except Exception as exc:
                failure = f"{name}: {exc}"
                print("ERROR recuperable:", failure, file=sys.stderr, flush=True)
                break
            up = page_updated(root)
            fs["latest_updated"] = max(fs.get("latest_updated", ""), up)
            nxt = page_next(root)
            # La carga inicial no se corta por fecha: recorre el histórico disponible.
            older = bool(mode == "incremental" and up and up[:10] < state["cycle_since"])
            fs["done"] = not nxt or older
            fs["next_url"] = None if fs["done"] else nxt
            budget -= 1
            save()
            if fs["done"]:
                print(f"{name}: feed terminado", flush=True)
                break
            time.sleep(0.5)
        if failure or budget == 0:
            break

    cycle_complete = all(state["feeds"][n].get("done") for n in FEEDS)
    if cycle_complete:
        if mode == "initial":
            state["mode"] = "incremental"
        state.pop("cycle_since", None)
        for fs in state["feeds"].values():
            fs["done"] = False
            fs["next_url"] = None
        save(complete=True)
        status = "complete"
    else:
        save(complete=False)
        status = "pending"
    status_path.write_text(status + "\n", "utf-8")
    print(f"STATUS={status} licitaciones={len(acc)}" + (f" error={failure}" if failure else ""), flush=True)


if __name__ == "__main__":
    main()
