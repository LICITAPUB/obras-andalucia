#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enriquece licitaciones de obras con datos del anuncio PLACSP y sus pliegos PDF.
Procesamiento incremental: cada ejecución analiza hasta --limit expedientes sin ficha
o cuya ficha haya caducado. Los resultados se guardan dentro de data/obras.json.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "obras.json"
UA = "Mozilla/5.0 (compatible; RadarObrasGuamar/1.0; +https://github.com/)"
TIMEOUT = 20
MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 250000

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        elif tag in ("p", "div", "tr", "li"):
            self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def clean(s):
    s = (s or "").replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()

def fetch(url, max_bytes=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        data = response.read((max_bytes or MAX_PDF_BYTES) + 1)
        if max_bytes and len(data) > max_bytes:
            raise ValueError("respuesta demasiado grande")
        return data, response.headers.get("Content-Type", "")

def html_text(raw):
    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", "replace"))
    return clean("".join(parser.parts))

def extract_pdf(raw):
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        chunks = []
        for page in reader.pages[:30]:
            chunks.append(page.extract_text() or "")
        return clean("\n".join(chunks))[:MAX_TEXT_CHARS]
    except Exception as exc:
        print("    PDF no legible:", exc, file=sys.stderr)
        return ""

def section(text, start, ends, maxlen=6000):
    m = re.search(start, text, re.I)
    if not m:
        return ""
    tail = text[m.end():]
    stops = [re.search(p, tail, re.I) for p in ends]
    stops = [x.start() for x in stops if x]
    return clean(tail[:min(stops) if stops else maxlen])[:maxlen]

def first_match(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.S)
        if m:
            return clean(m.group(1))
    return ""

def extract_ficha(text, source):
    t = clean(text)
    ficha = {}
    desc = section(t, r"Descripci[oó]n del procedimiento", [
        r"Valor estimado del contrato", r"Presupuesto base de licitaci[oó]n",
        r"Clasificaci[oó]n CPV", r"Plazo de ejecuci[oó]n"
    ], 3500)
    if desc:
        ficha["descripcion"] = desc

    clas = section(t, r"Clasificaci[oó]n empresarial solicitada", [
        r"Condiciones de admisi[oó]n", r"Criterio de solvencia", r"Preparaci[oó]n de oferta",
        r"Condiciones de adjudicaci[oó]n", r"Plazo de validez"
    ], 3000)
    if clas:
        lines = [x.strip(" •·-\t") for x in clas.splitlines() if x.strip()]
        ficha["clasificacion"] = "; ".join(lines[:12])
        ficha["clasificacion_items"] = lines[:12]
        ficha["clasificacion_estado"] = "localizada"
    elif re.search(r"Clasificaci[oó]n empresarial solicitada", t, re.I):
        ficha["clasificacion"] = "No se especifica clasificación empresarial en el apartado consultado."
        ficha["clasificacion_estado"] = "no_consta"
    else:
        ficha["clasificacion_estado"] = "no_localizada"

    # Los bloques de preparación de oferta suelen repetirse, uno por sobre.
    blocks = re.findall(
        r"Preparaci[oó]n de oferta\s*(.*?)(?=Preparaci[oó]n de oferta|Condiciones de adjudicaci[oó]n|Plazo de validez|Programas de financiaci[oó]n|Subcontrataci[oó]n|$)",
        t, re.I | re.S
    )
    sobres = []
    for b in blocks:
        name = first_match(b, [r"(Sobre\s+(?:[A-ZÁÉÍÓÚ]|Uno|Dos|Tres|[0-9]+))"])
        tipo = first_match(b, [r"Tipo de Oferta\s*(.*?)(?:Evento de Apertura|Descripci[oó]n|$)"])
        desc_s = first_match(b, [r"Descripci[oó]n\s*(.*?)(?:Evento de Apertura|$)"])
        if name or tipo or desc_s:
            item = {}
            if name: item["nombre"] = name
            if tipo: item["tipo"] = tipo[:300]
            if desc_s: item["descripcion"] = desc_s[:700]
            sobres.append(item)
    # Fallback: detect headings when the text extraction changes line ordering.
    if not sobres:
        found = re.findall(r"(Sobre\s+(?:[A-ZÁÉÍÓÚ]|Uno|Dos|Tres|[0-9]+))", t, re.I)
        unique = []
        for n in found:
            if n.lower() not in [x.lower() for x in unique]:
                unique.append(n)
        if unique:
            sobres = [{"nombre": n} for n in unique[:10]]
    if sobres:
        ficha["sobres"] = sobres
        ficha["numero_sobres"] = len(sobres)

    ficha["procedimiento"] = first_match(t, [
        r"(?:Proceso de Licitaci[oó]n\s*)?Procedimiento\s*(Abierto[^.\n]*|Restringido[^.\n]*|Negociado[^.\n]*|Di[aá]logo competitivo[^.\n]*|Asociaci[oó]n para la innovaci[oó]n[^.\n]*)"
    ])
    ficha["tramitacion"] = first_match(t, [r"Tramitaci[oó]n\s*(Ordinaria|Urgente|De emergencia)"])
    cpv = re.findall(r"\b(45\d{6})\s*[-–]\s*([^\n]+)", t)
    if cpv:
        ficha["cpv"] = list(dict.fromkeys([a + " - " + clean(b) for a,b in cpv]))[:15]
    duration = first_match(t, [r"Plazo de Ejecuci[oó]n\s*(\d+\s*(?:D[ií]a|Mes|A[nñ]o)\w*)"])
    if duration:
        ficha["duracion"] = duration
    guarantee = first_match(t, [r"Garant[ií]a Requerida Definitiva\s*(?:Porcentaje\s*)?([0-9]+(?:[.,][0-9]+)?\s*%)"])
    if guarantee:
        ficha["garantia"] = guarantee + " definitiva"
    if re.search(r"Contrato Sujeto a regulaci[oó]n armonizada\s+S[ií]", t, re.I):
        ficha["sara"] = "Sujeto a regulación armonizada"
    elif re.search(r"Contrato Sujeto a regulaci[oó]n armonizada\s+No", t, re.I):
        ficha["sara"] = "No sujeto a regulación armonizada"
    finance = section(t, r"Programas de Financiaci[oó]n", [
        r"Subcontrataci[oó]n permitida", r"Proceso de Licitaci[oó]n", r"ID\s+\d+"
    ], 1800)
    if finance:
        ficha["financiacion"] = finance
    criteria = section(t, r"Criterios de Adjudicaci[oó]n", [
        r"Plazo de Validez de la Oferta", r"Presentaci[oó]n de recursos",
        r"Programas de Financiaci[oó]n", r"Subcontrataci[oó]n permitida"
    ], 5000)
    if criteria:
        ficha["criterios"] = [x.strip(" •·-") for x in criteria.splitlines() if x.strip()][:25]
    conditions = section(t, r"Condiciones especiales de ejecuci[oó]n de Contrato", [
        r"Requisitos de participaci[oó]n", r"Condiciones de Licitaci[oó]n",
        r"Garant[ií]a Requerida", r"Programas de Financiaci[oó]n"
    ], 2500)
    if conditions:
        ficha["condiciones"] = [x.strip(" •·-") for x in conditions.splitlines() if x.strip()][:12]
    ficha["fuente"] = source
    ficha["analizado_en"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ficha["estado_analisis"] = "completo" if (desc or clas or sobres or cpv) else "parcial"
    return ficha

def doc_url(doc, prefixes):
    try:
        _, _, ix, suffix, *rest = doc
        ix = int(ix)
        if ix >= 0 and ix < len(prefixes):
            return prefixes[ix] + suffix
        return suffix if suffix.startswith("http") else ""
    except Exception:
        return ""

def enrich(record, prefixes):
    texts, sources, errors = [], [], []
    detail = record.get("u")
    if detail:
        try:
            raw, _ = fetch(detail, 3 * 1024 * 1024)
            texts.append(html_text(raw))
            sources.append(detail)
        except Exception as exc:
            errors.append("anuncio: " + str(exc))
    docs = record.get("dc") or []
    # El PCAP (documento legal) es prioritario; después el PPT y anexos.
    ordered = sorted(docs, key=lambda x: (0 if x and x[0] == "L" else 1 if x and x[0] == "T" else 2))
    pdf_count = 0
    for doc in ordered:
        if pdf_count >= 2:
            break
        url = doc_url(doc, prefixes)
        if not url:
            continue
        name = (doc[1] if len(doc)>1 else "").lower()
        # Solo descargar formatos PDF o documentos cuyo nombre sugiera pliego.
        if name and not (name.endswith(".pdf") or any(k in name for k in ("pliego", "pcap", "administrativ"))):
            continue
        try:
            raw, ctype = fetch(url, MAX_PDF_BYTES)
            if raw[:4] != b"%PDF" and "pdf" not in ctype.lower():
                continue
            txt = extract_pdf(raw)
            if txt:
                texts.append(txt)
                sources.append(url)
                pdf_count += 1
            time.sleep(0.4)
        except Exception as exc:
            errors.append("documento " + (doc[1] if len(doc)>1 else "") + ": " + str(exc)[:160])
    combined = "\n".join(texts)
    if not combined:
        return None, errors or ["No se pudo recuperar el anuncio ni los pliegos."]
    ficha = extract_ficha(combined, "Anuncio PLACSP y documentación enlazada")
    ficha["documentos_consultados"] = len(sources)
    ficha["fuentes"] = sources[:5]
    ficha["errores_consulta"] = errors[:5]
    if ficha.get("estado_analisis") != "completo" and errors:
        ficha["estado_analisis"] = "parcial"
    # Un expediente que ya tenía una ficha mejor no debe perderla por una descarga incompleta.
    return ficha, errors

def save_json_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), "utf-8")
    os.replace(temp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20, help="máximo de expedientes por ejecución")
    ap.add_argument("--refresh-days", type=int, default=30, help="volver a analizar fichas más antiguas")
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--out", default=str(DATA))
    args = ap.parse_args()
    path = Path(args.out)
    payload = json.loads(path.read_text("utf-8"))
    records = payload.get("D", [])
    prefixes = payload.get("px", [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.refresh_days)
    pending = []
    now = datetime.now(timezone.utc)
    for r in records:
        f = r.get("ficha") or {}
        status = f.get("estado_analisis", "")
        stamp = f.get("analizado_en", "")
        try:
            last = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
        except Exception:
            last = None
        if not f or status == "pendiente":
            pending.append(r)
        elif status == "error":
            if last is None or last < now - timedelta(days=7):
                pending.append(r)
        elif last is None or last < cutoff:
            pending.append(r)
    # Prioriza licitaciones recientes y las que continúan en plazo.
    pending.sort(key=lambda r: (r.get("est") == "En plazo", r.get("up","")), reverse=True)
    selected = pending[:max(0,args.limit)]
    print(f"Fichas existentes: {len(records)-len(pending)} | pendientes: {len(pending)} | a analizar ahora: {len(selected)}")
    ok = 0
    for i, r in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {r.get('id')} · {r.get('t','')[:90]}")
        try:
            ficha, errors = enrich(r, prefixes)
            if ficha:
                previous = r.get("ficha") or {}
                # Conservar campos previos que no se hayan podido recuperar en la nueva pasada.
                for key, value in previous.items():
                    if key not in ficha or not ficha.get(key):
                        ficha[key] = value
                r["ficha"] = ficha
                ok += 1
                print("   ->", ficha.get("estado_analisis"), "| clasificación:", ficha.get("clasificacion_estado","pendiente"),
                      "| sobres:", ficha.get("numero_sobres","no localizados"))
            else:
                r["ficha"] = {"estado_analisis":"error", "analizado_en":datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "errores_consulta":errors[:5], "fuente":"No se pudo recuperar la documentación"}
                print("   -> sin datos", "; ".join(errors[:2]))
        except Exception as exc:
            r["ficha"] = {"estado_analisis":"error", "analizado_en":datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "errores_consulta":[str(exc)[:300]]}
            print("   -> ERROR:", exc, file=sys.stderr)
        payload["fichas_actualizadas"] = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        payload["fichas_procesadas_total"] = sum(1 for item in records if item.get("ficha"))
        save_json_atomic(path, payload)
        time.sleep(max(0,args.delay))
    payload["fichas_actualizadas"] = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    payload["fichas_procesadas_total"] = sum(1 for r in records if r.get("ficha"))
    save_json_atomic(path, payload)
    print(f"Resultado: {ok}/{len(selected)} expedientes enriquecidos. Total con ficha: {payload['fichas_procesadas_total']}/{len(records)}")

if __name__ == "__main__":
    main()
