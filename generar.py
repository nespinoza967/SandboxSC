"""Genera el Sandbox de precios de SIPCO: tiendas virtuales con precios simulados, listas para GitHub Pages.

Uso:  python generar.py [--semana 2026-W45] [--salida sitio] [--caida aceros-norte-v,...]

Cada tienda de datos/tiendas.json parte de los precios de datos/precios_promedios_v.csv y les aplica su factor y una
variación semanal simulada. La variación sale de una semilla (semana, tienda, producto): la misma semana genera
siempre los mismos precios, así SIPCO se prueba contra precios conocidos (indicador D3, esperados.csv).

Cada tienda publica según su tipo de fuente, como lo lee SIPCO (HU-19):
  HTML     <tienda>/index.html        tabla con filas <tr data-sku data-precio data-largo>
  API      <tienda>/api/precios.json  {"productos": [{"sku", "nombre", "precio_clp", "largo_m", "url"}]}
  ARCHIVO  <tienda>/precios.csv       sku,nombre,precio_clp,largo_m
--caida deja sin publicar la fuente de esas tiendas (SIPCO recibe 404): sirve para probar lecturas parciales.
"""

import argparse
import csv
import datetime as dt
import html
import io
import json
import random
import shutil
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BASE = RAIZ / "datos" / "precios_promedios_v.csv"
TIENDAS = RAIZ / "datos" / "tiendas.json"
IVA = Decimal("1.19")
RUTA_FUENTE = {"HTML": "index.html", "API": "api/precios.json", "ARCHIVO": "precios.csv"}


def semana_iso(fecha):
    anio, semana, _ = fecha.isocalendar()
    return f"{anio}-W{semana:02d}"


def proxima_semana(hoy=None):
    """Semana que empieza el próximo lunes (el Action corre el domingo y SIPCO lee el lunes a las 00:00)."""
    hoy = hoy or dt.date.today()
    return semana_iso(hoy + dt.timedelta(days=7 - hoy.weekday()))


def leer_base(ruta=BASE):
    with open(ruta, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def leer_tiendas(ruta=TIENDAS):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))["tiendas"]


def sku(tienda, producto):
    prefijo = "".join(p[0] for p in tienda["codigo"].split("-")[:2]).upper()
    return f"{prefijo}-{producto['codigo'].split('-')[1]}"


def vende(tienda, producto):
    """Qué productos vende cada tienda: fijo entre semanas, para que un producto no desaparezca al azar."""
    return random.Random(f"{tienda['codigo']}|{producto['codigo']}").random() < tienda["cobertura"]


def precio(tienda, producto, semana):
    """Precio publicado de la semana en CLP: con IVA si la tienda publica así, si no neto (precio base ÷ 1,19)."""
    variacion = random.Random(f"{semana}|{tienda['codigo']}|{producto['codigo']}").uniform(-1, 1)
    valor = (Decimal(producto["precio_base_clp"]) * Decimal(str(tienda["factor"]))
             * (1 + Decimal(str(round(variacion * tienda["variacion_pct"], 4))) / 100))
    if not tienda["publica_con_iva"]:
        valor = valor / IVA
    paso = Decimal(10) if tienda["publica_con_iva"] else Decimal(1)  # al público se redondea a la decena
    return int((valor / paso).quantize(Decimal(1), ROUND_HALF_UP) * paso)


def productos_de(tienda, base, semana):
    return [{"sku": sku(tienda, p), "codigo": p["codigo"], "nombre": p["nombre"], "precio_clp": precio(tienda, p, semana),
             "largo_m": p["largo_m"], "designacion_icha": p["designacion_icha"]}
            for p in base if vende(tienda, p)]


def pesos(n):
    return f"${n:,}".replace(",", ".")


def _html_tienda(tienda, productos, semana):
    filas = "\n".join(
        f'      <tr id="{p["sku"]}" data-sku="{p["sku"]}" data-precio="{p["precio_clp"]}" data-largo="{p["largo_m"]}">'
        f'<td>{p["sku"]}</td><td>{html.escape(p["nombre"])}</td><td>{p["largo_m"] or "—"} m</td>'
        f'<td>{pesos(p["precio_clp"])}</td></tr>'
        for p in productos)
    iva = "Precios con IVA incluido." if tienda["publica_con_iva"] else "Precios netos (sin IVA)."
    return f"""<!doctype html>
<html lang="es-CL"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(tienda["nombre"])}</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#1e293b}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #e2e8f0;padding:.4rem;text-align:left}}.aviso{{background:#fef3c7;padding:.5rem}}</style>
</head><body>
<p class="aviso">Tienda virtual del Sandbox de SIPCO: precios simulados, no es una tienda real.</p>
<h1>{html.escape(tienda["nombre"])}</h1>
<p>Semana {semana}. {iva}</p>
<table>
  <thead><tr><th>SKU</th><th>Producto</th><th>Largo</th><th>Precio</th></tr></thead>
  <tbody>
{filas}
  </tbody>
</table>
</body></html>
"""


def _csv(campos, filas):
    salida = io.StringIO()
    w = csv.DictWriter(salida, fieldnames=campos, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(filas)
    return salida.getvalue()


def generar(salida, semana, caidas=(), base=None, tiendas=None):
    base = base if base is not None else leer_base()
    tiendas = tiendas if tiendas is not None else leer_tiendas()
    salida = Path(salida)
    if salida.exists():
        shutil.rmtree(salida)
    salida.mkdir(parents=True)
    indice, mapeo, esperados = [], [], []
    for t in tiendas:
        productos = productos_de(t, base, semana)
        carpeta = salida / t["codigo"]
        ruta = RUTA_FUENTE[t["tipo_fuente"]]
        for p in productos:
            p["url"] = f"{t['codigo']}/index.html#{p['sku']}" if t["tipo_fuente"] == "HTML" else ""
            if p["designacion_icha"]:
                mapeo.append({"tienda": t["codigo"], "sku": p["sku"], "url": p["url"],
                              "designacion_icha": p["designacion_icha"]})
            esperados.append({"tienda": t["codigo"], "sku": p["sku"], "precio_clp": p["precio_clp"],
                              "largo_m": p["largo_m"]})
        indice.append({k: t[k] for k in ("codigo", "nombre", "tipo_fuente", "publica_con_iva")}
                      | {"url_fuente": f"{t['codigo']}/{ruta}", "productos": len(productos),
                         "disponible": t["codigo"] not in caidas})
        if t["codigo"] in caidas:
            continue
        destino = carpeta / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        if t["tipo_fuente"] == "HTML":
            destino.write_text(_html_tienda(t, productos, semana), encoding="utf-8")
        elif t["tipo_fuente"] == "API":
            destino.write_text(json.dumps(
                {"tienda": t["nombre"], "semana": semana, "con_iva": t["publica_con_iva"],
                 "productos": [{k: p[k] for k in ("sku", "nombre", "precio_clp", "largo_m", "url")} for p in productos]},
                ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            destino.write_text(_csv(["sku", "nombre", "precio_clp", "largo_m"], productos), encoding="utf-8")

    generado = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (salida / "tiendas.json").write_text(json.dumps(
        {"semana": semana, "generado_en": generado, "tiendas": indice}, ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "productos.csv").write_text(_csv(["tienda", "sku", "url", "designacion_icha"], mapeo), encoding="utf-8")
    (salida / "esperados.csv").write_text(_csv(["tienda", "sku", "precio_clp", "largo_m"], esperados), encoding="utf-8")
    enlaces = "\n".join(
        f'<li><a href="{html.escape(i["url_fuente"])}">{html.escape(i["nombre"])}</a> — {i["tipo_fuente"]}, '
        f'{"con" if i["publica_con_iva"] else "sin"} IVA, {i["productos"]} productos'
        f'{"" if i["disponible"] else " (sin publicar esta semana)"}</li>' for i in indice)
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es-CL"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sandbox de precios SIPCO</title><style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#1e293b}}</style>
</head><body>
<h1>Sandbox de precios SIPCO</h1>
<p>Tiendas virtuales con precios simulados para la lectura semanal de SIPCO (HU-19). Semana {semana}.</p>
<ul>
{enlaces}
</ul>
<p><a href="tiendas.json">tiendas.json</a> · <a href="productos.csv">productos.csv</a> ·
<a href="esperados.csv">esperados.csv</a></p>
</body></html>
""", encoding="utf-8")
    return indice


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--semana", default=None, help="semana ISO, ej. 2026-W45 (por defecto, la del próximo lunes)")
    ap.add_argument("--salida", default=str(RAIZ / "sitio"))
    ap.add_argument("--caida", default="", help="códigos de tienda separados por coma que no publican esta semana")
    args = ap.parse_args(argv)
    semana = args.semana or proxima_semana()
    caidas = {c.strip() for c in args.caida.split(",") if c.strip()}
    for t in generar(args.salida, semana, caidas):
        estado = "publicada" if t["disponible"] else "SIN PUBLICAR"
        print(f"{t['nombre']}: {t['productos']} productos ({t['tipo_fuente']}), {estado}")
    print(f"Semana {semana} -> {args.salida}")


if __name__ == "__main__":
    main()
