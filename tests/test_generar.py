"""Pruebas del generador de tiendas virtuales. Ejecutar: python -m pytest tests"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generar as g  # noqa: E402


def test_base_sin_datos_de_la_tienda_de_origen():
    base = g.leer_base()
    assert len(base) == 142 and len({p["codigo"] for p in base}) == 142
    assert sum(1 for p in base if p["designacion_icha"]) == 78
    assert "http" not in g.BASE.read_text(encoding="utf-8")  # sin URL de la tienda de origen
    assert list(base[0]) == ["codigo", "nombre", "tipo", "dimensiones", "espesor_mm", "largo_m", "proceso",
                             "precio_base_clp", "designacion_icha"]


def test_misma_semana_mismos_precios_y_otra_semana_cambia(tmp_path):
    t = g.leer_tiendas()[0]
    p = g.leer_base()[10]
    assert g.precio(t, p, "2026-W45") == g.precio(t, p, "2026-W45")
    assert any(g.precio(t, q, "2026-W45") != g.precio(t, q, "2026-W46") for q in g.leer_base()[:10])


def test_variacion_dentro_del_rango_de_la_tienda():
    for t in g.leer_tiendas():
        for p in g.leer_base():
            base = int(p["precio_base_clp"]) * t["factor"] / (1 if t["publica_con_iva"] else 1.19)
            margen = base * t["variacion_pct"] / 100 + 10
            assert abs(g.precio(t, p, "2026-W45") - base) <= margen, (t["codigo"], p["codigo"])


def test_tienda_sin_iva_publica_neto():
    con, sin = [{"codigo": c, "factor": 1.0, "variacion_pct": 0, "publica_con_iva": i} for c, i in (("a", True), ("b", False))]
    p = {"codigo": "PPV-001", "precio_base_clp": "11900"}
    assert (g.precio(con, p, "2026-W45"), g.precio(sin, p, "2026-W45")) == (11900, 10000)


def test_cobertura_fija_entre_semanas():
    t = g.leer_tiendas()[2]
    base = g.leer_base()
    assert [g.vende(t, p) for p in base] == [g.vende(t, p) for p in base]
    assert 0.5 < sum(g.vende(t, p) for p in base) / len(base) < 0.9


def test_genera_cada_fuente_y_los_archivos_para_sipco(tmp_path):
    g.generar(tmp_path, "2026-W45")
    indice = json.loads((tmp_path / "tiendas.json").read_text(encoding="utf-8"))
    assert indice["semana"] == "2026-W45"
    fuentes = {t["tipo_fuente"]: tmp_path / t["url_fuente"] for t in indice["tiendas"]}
    assert set(fuentes) == {"HTML", "API", "ARCHIVO"} and all(f.exists() for f in fuentes.values())
    assert 'data-sku="AN-001" data-precio="' in fuentes["HTML"].read_text(encoding="utf-8")
    api = json.loads(fuentes["API"].read_text(encoding="utf-8"))
    assert api["con_iva"] is False and {"sku", "precio_clp", "largo_m"} <= set(api["productos"][0])
    archivo = list(csv.DictReader(fuentes["ARCHIVO"].open(encoding="utf-8")))
    assert list(archivo[0]) == ["sku", "nombre", "precio_clp", "largo_m"]
    mapeo = list(csv.DictReader((tmp_path / "productos.csv").open(encoding="utf-8")))
    assert mapeo and all(m["designacion_icha"] for m in mapeo)
    esperados = list(csv.DictReader((tmp_path / "esperados.csv").open(encoding="utf-8")))
    assert len(esperados) == sum(t["productos"] for t in indice["tiendas"])


def test_tienda_caida_no_publica_su_fuente(tmp_path):
    g.generar(tmp_path, "2026-W45", caidas={"ferreteria-pampa-v"})
    indice = {t["codigo"]: t for t in json.loads((tmp_path / "tiendas.json").read_text(encoding="utf-8"))["tiendas"]}
    assert indice["ferreteria-pampa-v"]["disponible"] is False
    assert not (tmp_path / indice["ferreteria-pampa-v"]["url_fuente"]).exists()
    assert (tmp_path / indice["aceros-norte-v"]["url_fuente"]).exists()


def test_proxima_semana_es_la_del_lunes_siguiente():
    assert g.proxima_semana(dt.date(2026, 11, 1)) == "2026-W45"  # domingo -> lunes 2 de noviembre
    assert g.proxima_semana(dt.date(2026, 11, 2)) == "2026-W46"
