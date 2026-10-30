"""Scraper simple de precios de perfiles de acero en sodimac.cl -> CSV (append).

Uso:  py scripts/sodimac/scrapear.py [--salida precios_sodimac.csv] [--paginas 5] [--terminos N|t1,t2]
      py scripts/sodimac/scrapear.py --reprocesar precios_sodimac_v2.csv [--salida nuevo.csv]

Mismo criterio que backend/precios/sodimac.py: respeta robots.txt, User-Agent realista,
pausa entre páginas, y lee datos estructurados (__NEXT_DATA__ del listado y, como respaldo,
JSON-LD schema.org Product). No inventa datos: si el sitio bloquea, informa y termina.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import random
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.robotparser
from pathlib import Path

import requests

BASE = "https://www.sodimac.cl"
BUSQUEDA = BASE + "/sodimac-cl/buscar?Ntt={q}&page={p}"
TERMINOS = ["perfil angulo acero", "angulo laminado", "angulo plegado", "perfil canal acero",
            "perfil costanera acero", "perfil cuadrado acero", "perfil rectangular acero",
            "tubo cuadrado acero", "tubo redondo acero", "pletina acero", "fierro redondo",
            "fierro cuadrado", "barra lisa", "plancha acero", "viga acero", "perfil T acero",
            "perfil acero"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
ESPERA_MIN_S, ESPERA_MAX_S = 8, 15  # pausa con jitter entre requests
MAX_REQUESTS = 80  # tope duro por ejecución
MAX_PAGINAS = 5  # páginas por término (se corta antes si no hay productos nuevos)
CACHE = Path(__file__).with_name(".cache")
CAMPOS = ["fecha", "termino", "nombre", "sku", "precio_clp", "url",
          "tipo", "dimensiones", "espesor_mm", "largo_m", "proceso", "observacion"]
_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_LDJSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)

# --- Clasificación / filtro -------------------------------------------------------------
_TIPOS = [("tubo_redondo", r"tubular redond|\btubo redond"), ("pletina", r"pletina|\bplan[oa]\b"),
          ("barra_a63", r"\ba-?63\b"), ("barra_redonda", r"\bfierro (liso )?redond|barra lisa"),
          ("barra_cuadrada", r"\bfierro (liso )?cuadrad"), ("costanera", r"costanera"), ("canal", r"\bcanal\b"), ("angulo", r"\bangulo\b"),
          ("pletina", r"pletina"), ("plancha", r"plancha"), ("viga", r"\bviga\b"),
          ("perfil_t", r"\bperfil t\b|\btee\b"), ("cuadrado", r"cuadrad"),
          ("rectangular", r"rectangular"), ("redondo", r"redond|barra lisa|\btubo\b")]
_ACERO = re.compile(r"\bacero\b|\bfierro\b|\ba-?63\b|\ba-?37\b|\bgalvanizad|\blaminad[oa]\b|\bplegad[oa]\b")
_EXCLUIR = re.compile(r"aluminio|madera|\bpino\b|oregon|radiata|terciado|decorativ|acabado|"
                      r"\bblanco\b|\bnegro\b|\bcafe\b|esquinero|ceramica|soporte|asiento|union|"
                      r"conector|detector|buscador|filtro|velador|comoda|closet|tornillo|clavo|"
                      r"martillo|barniz|canaleta|rejilla|ducha|carrito|fijacion|inoxidable")
_DIM = re.compile(r"(\d+(?:[.,]\d+)?(?:\s*x\s*\d+(?:[.,]\d+)?)+)\s*mm")
_DIM_SUELTA = re.compile(r"(\d+(?:[.,]\d+)?)\s*mm")
_LARGO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:m|mt|mts|metros?)\b")


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


def _num(txt):
    return float(txt.replace(",", "."))


_PULG = re.compile(r'(\d+(?:\s+\d+/\d+)?|\d+/\d+)\s*"')
_PLANCHA = re.compile(r"(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)\s*(?:mt|mts|m)\b(?:\s*x)?\s*(\d+(?:[.,]\d+)?)\s*mm")


def _fmt(x):
    return ("%g" % x)


def clasificar(nombre):
    """Devuelve dict con tipo, dimensiones, espesor_mm, largo_m, proceso, observacion."""
    t = normalizar(nombre)
    tipo = next((k for k, pat in _TIPOS if re.search(pat, t)), "")
    proceso = "laminado" if "laminad" in t else "plegado" if "plegad" in t else ""
    dims, espesor, largo, obs = "", "", "", ""
    if not tipo and re.search(r"\bfierro\b|\bbarra\b", t):  # respaldo genérico
        tipo = "barra_redonda"
    mp = _PLANCHA.search(t) if tipo == "plancha" else None
    if mp:  # "3,0 x 1,0mt x 1,5mm" / "0.25x2 m 0.30 mm": metros -> mm
        a, b = _num(mp.group(1)), _num(mp.group(2))
        largo, ancho = max(a, b), min(a, b)
        dims = f"{_fmt(largo * 1000)}x{_fmt(ancho * 1000)}"
        espesor = _num(mp.group(3))
        return {"tipo": tipo, "dimensiones": dims, "espesor_mm": espesor, "largo_m": largo,
                "proceso": proceso, "observacion": obs}
    if tipo == "tubo_redondo":  # 'Perfil Tubular Redondo Acero 1 1/4" 2 mm 6 m'
        mq = _PULG.search(nombre)
        if mq:
            dims = mq.group(1).strip() + '"'
            resto = nombre[mq.end():].replace(",", ".")
            me = _DIM_SUELTA.search(resto)
            if me:
                espesor = _num(me.group(1))
            lm = _LARGO.search(resto[me.end():] if me else resto)
            largo = _num(lm.group(1)) if lm else ""
        return {"tipo": tipo, "dimensiones": dims, "espesor_mm": espesor, "largo_m": largo,
                "proceso": proceso, "observacion": obs}
    m = _DIM.search(t)
    if m:
        partes = [p.strip().replace(",", ".") for p in m.group(1).split("x")]
        if tipo.startswith("barra_") and len(partes) == 2 and partes[0] == partes[1]:
            dims = partes[0]  # "12x12 mm" en barras = diámetro/lado 12
        else:
            dims = "x".join(partes)
        if tipo == "pletina" and len(partes) == 2:
            espesor = _num(partes[0])  # "3x50": espesor x ancho
        elif len(partes) >= 3 or (tipo == "plancha" and len(partes) >= 2):
            espesor = _num(partes[-1])
            lado = min(_num(p) for p in partes[:-1])
            if espesor >= lado / 2 and espesor / 10 < lado / 2:  # ej. 25x25x15 -> 1.5
                obs = f"espesor {_fmt(espesor)} implausible para lado {_fmt(lado)}; se asume {_fmt(espesor / 10)}"
                espesor = espesor / 10
                partes[-1] = _fmt(espesor)
                dims = "x".join(partes)
    else:
        m = _DIM_SUELTA.search(t)
        if m:
            dims = m.group(1).replace(",", ".")
            if tipo == "plancha":
                espesor = _num(m.group(1))
    resto = t[m.end():] if m else t
    lm = _LARGO.search(resto)
    largo = _num(lm.group(1)) if lm else ""
    return {"tipo": tipo, "dimensiones": dims, "espesor_mm": espesor, "largo_m": largo,
            "proceso": proceso, "observacion": obs}


def reprocesar(entrada, salida=None):
    """Re-clasifica un CSV existente (sin red) y escribe un CSV nuevo con las columnas actuales."""
    entrada = Path(entrada)
    salida = Path(salida) if salida else entrada.with_name(entrada.stem + "_reprocesado" + entrada.suffix)
    with entrada.open(encoding="utf-8", newline="") as fh:
        filas = list(csv.DictReader(fh))
    with salida.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS, extrasaction="ignore")
        w.writeheader()
        for f in filas:
            w.writerow({**{k: f.get(k, "") for k in CAMPOS}, **clasificar(f.get("nombre", ""))})
    return salida, len(filas)


def es_acero(nombre):
    """True si el nombre parece un perfil/barra/plancha de acero (no aluminio, madera, decorativo...)."""
    t = normalizar(nombre)
    if _EXCLUIR.search(t) or not _ACERO.search(t):
        return False
    return bool(clasificar(nombre)["tipo"])


def total_paginas(html):
    """Lee la paginación de __NEXT_DATA__ (pageProps.pagination) si existe; si no, None."""
    m = _NEXT.search(html)
    if not m:
        return None
    try:
        props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
    except ValueError:
        return None
    pag = props.get("pagination") or props.get("searchResults", {}).get("pagination") or {}
    if not isinstance(pag, dict):
        return None
    for k in ("totalPages", "pages", "pageCount"):
        if isinstance(pag.get(k), int):
            return pag[k]
    total, por = pag.get("count") or pag.get("total"), pag.get("perPage") or pag.get("pageSize")
    if isinstance(total, int) and isinstance(por, int) and por > 0:
        return -(-total // por)
    return None


def elegir_terminos(valor):
    """--terminos: número N (primeros N) o lista separada por comas de términos."""
    if valor is None:
        return list(TERMINOS)
    valor = valor.strip()
    if valor.isdigit():
        return TERMINOS[:int(valor)]
    return [x.strip() for x in valor.split(",") if x.strip()]


def _a_entero(valor):
    if isinstance(valor, list):
        valor = valor[0] if valor else None
    digitos = re.sub(r"[^\d]", "", str(valor or "").split(",")[0])
    return int(digitos) if digitos else None


def desde_next_data(html):
    m = _NEXT.search(html)
    if not m:
        return []
    try:
        datos = json.loads(m.group(1))
    except ValueError:
        return []
    resultados = (datos.get("props", {}).get("pageProps", {}).get("results")) or []
    filas = []
    for r in resultados:
        precios = r.get("prices") or []
        # Preferir precio normal/oferta del primer bloque con valor.
        precio = next((_a_entero(p.get("price")) for p in precios if _a_entero(p.get("price"))), None)
        if precio:
            filas.append({"nombre": r.get("displayName", ""), "sku": r.get("skuId") or r.get("productId", ""),
                          "precio_clp": precio, "url": urllib.parse.urljoin(BASE, r.get("url", ""))})
    return filas


def _productos(dato):
    if isinstance(dato, list):
        for d in dato:
            yield from _productos(d)
    elif isinstance(dato, dict):
        if dato.get("@type") == "Product":
            yield dato
        yield from _productos(dato.get("@graph"))
        yield from _productos(dato.get("itemListElement"))
        yield from _productos(dato.get("item"))


def desde_json_ld(html):
    filas = []
    for bloque in _LDJSON.findall(html):
        try:
            dato = json.loads(bloque)
        except ValueError:
            continue
        for p in _productos(dato):
            ofertas = p.get("offers") or {}
            if isinstance(ofertas, list):
                ofertas = ofertas[0] if ofertas else {}
            precio = _a_entero(ofertas.get("price") or ofertas.get("lowPrice"))
            if precio:
                filas.append({"nombre": p.get("name", ""), "sku": str(p.get("sku", "")),
                              "precio_clp": precio, "url": urllib.parse.urljoin(BASE, p.get("url", ""))})
    return filas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default=str(Path(__file__).with_name("precios_sodimac.csv")))
    ap.add_argument("--paginas", type=int, default=MAX_PAGINAS, help="máx. páginas por término")
    ap.add_argument("--max-requests", type=int, default=MAX_REQUESTS, help="tope de requests por ejecución")
    ap.add_argument("--terminos", default=None,
                    help="N (usar los N primeros) o lista separada por comas, ej. 'pletina acero,barra lisa'")
    ap.add_argument("--sin-filtro", action="store_true", help="no descartar productos que no son acero")
    ap.add_argument("--cache", action="store_true", help="guardar/reusar HTML en .cache (desarrollo)")
    ap.add_argument("--reprocesar", metavar="CSV", default=None,
                    help="re-parsear un CSV existente sin red; escribe en --salida o <csv>_reprocesado.csv")
    args = ap.parse_args(argv)
    if args.reprocesar:
        salida = args.salida if "--salida" in (argv if argv is not None else sys.argv) else None
        ruta, n = reprocesar(args.reprocesar, salida)
        print(f"{n} filas reprocesadas -> {ruta}")
        return
    terminos = elegir_terminos(args.terminos)
    estimado = min(len(terminos) * args.paginas, args.max_requests)
    print(f"Términos ({len(terminos)}): {', '.join(terminos)}")
    print(f"Hasta {estimado} requests; duración estimada máx. ~{estimado * ESPERA_MIN_S // 60}-"
          f"{estimado * ESPERA_MAX_S // 60 + 1} min (suele ser menos: corta al no haber productos nuevos).")
    pedidos = 0

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9",
                      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    try:
        r = s.get(BASE + "/robots.txt", timeout=20)
    except requests.RequestException as e:
        sys.exit(f"No se pudo conectar a sodimac.cl: {e}")
    if r.status_code != 200:
        sys.exit(f"robots.txt respondió {r.status_code}; no se continúa. Inicio: {r.text[:200]!r}")
    robots = urllib.robotparser.RobotFileParser()
    robots.parse(r.text.splitlines())

    ahora = dt.datetime.now().isoformat(timespec="seconds")
    vistos, filas, excluidos, tope = set(), [], 0, False
    for i, termino in enumerate(terminos, 1):
        if tope:
            break
        for pagina in range(1, args.paginas + 1):
            url = BUSQUEDA.format(q=urllib.parse.quote_plus(termino), p=pagina)
            if not robots.can_fetch(UA, url):
                print(f"[robots.txt] no permitido: {url}")
                break
            archivo = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".html")
            if args.cache and archivo.exists():
                html = archivo.read_text(encoding="utf-8")
            else:
                if pedidos >= args.max_requests:
                    print(f"Tope de {args.max_requests} requests alcanzado; se detiene.")
                    tope = True
                    break
                time.sleep(random.uniform(ESPERA_MIN_S, ESPERA_MAX_S))
                pedidos += 1
                try:
                    resp = s.get(url, timeout=30)
                except requests.RequestException as e:
                    sys.exit(f"[error] {url}: {e} -- se detiene.")
                if resp.status_code != 200:
                    sys.exit(f"[{resp.status_code}] {url} -> {resp.text[:200]!r} -- se detiene (posible bloqueo).")
                html = resp.text
                if "captcha" in html.lower():
                    sys.exit("Captcha detectado; se detiene.")
                if args.cache:
                    CACHE.mkdir(exist_ok=True)
                    archivo.write_text(html, encoding="utf-8")
            encontrados = desde_next_data(html) or desde_json_ld(html)
            if not encontrados:
                if "akamai" in html.lower():
                    sys.exit("Posible bloqueo Akamai; se detiene.")
                print(f"[{i}/{len(terminos)}] {termino!r} pág {pagina}: sin productos")
                break
            nuevos = 0
            for f in encontrados:
                clave = f["sku"] or f["url"]
                if clave in vistos:
                    continue
                vistos.add(clave)
                nuevos += 1
                if not args.sin_filtro and not es_acero(f["nombre"]):
                    excluidos += 1
                    continue
                filas.append({"fecha": ahora, "termino": termino, **f, **clasificar(f["nombre"])})
            print(f"[{i}/{len(terminos)}] {termino!r} pág {pagina}: {len(encontrados)} productos, "
                  f"{nuevos} nuevos | acumulado {len(filas)} acero, {excluidos} excluidos, {pedidos} requests")
            total = total_paginas(html)
            if nuevos == 0 or (total is not None and pagina >= total):
                break

    salida = Path(args.salida)
    nuevo = not salida.exists()
    if not nuevo:  # CSV antiguo con otras columnas: no mezclar formatos
        with salida.open(encoding="utf-8") as fh:
            if fh.readline().strip().split(",") != CAMPOS:
                salida = salida.with_name(salida.stem + "_v3" + salida.suffix)
                nuevo = not salida.exists()
                print(f"El CSV existente tiene otras columnas; se escribe en {salida}")
    with salida.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        if nuevo:
            w.writeheader()
        w.writerows(filas)
    print(f"{len(filas)} filas agregadas a {salida} ({excluidos} excluidos por no ser acero, {pedidos} requests)")


if __name__ == "__main__":
    main()
