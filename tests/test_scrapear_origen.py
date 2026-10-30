"""Pruebas de parseo/filtro con nombres reales (tests/muestra_origen.csv). Ejecutar:
python -m pytest tests"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "herramientas"))
import scrapear_origen as s  # noqa: E402

MUESTRA = Path(__file__).with_name("muestra_origen.csv")


def test_clasificar_angulo_laminado():
    assert s.clasificar("Ángulo Laminado Acero 65x65x5mm 6 m") == {
        "tipo": "angulo", "dimensiones": "65x65x5", "espesor_mm": 5.0, "largo_m": 6.0, "proceso": "laminado",
        "observacion": ""}


def test_clasificar_varios():
    c = s.clasificar("Perfil Costanera Acero 80x40x15x2 mm 6 m")
    assert (c["tipo"], c["dimensiones"], c["espesor_mm"], c["largo_m"]) == ("costanera", "80x40x15x2", 2.0, 6.0)
    c = s.clasificar("Perfil Cuadrado Acero 30x30x1,5 mm 6 m")
    assert (c["tipo"], c["dimensiones"], c["espesor_mm"]) == ("cuadrado", "30x30x1.5", 1.5)
    assert s.clasificar("Ángulo Plegado Acero 50x50x2mm 6 m")["proceso"] == "plegado"
    assert s.clasificar("Perfil Rectangular Acero 40x20x2 mm 3 m")["largo_m"] == 3.0
    assert s.clasificar("Perfil Canal Acero 100x50x3mm 6 m")["tipo"] == "canal"
    c = s.clasificar("Fierro A-63 8x8 mm 6 m")
    assert (c["tipo"], c["dimensiones"], c["largo_m"]) == ("barra_a63", "8", 6.0)


def test_filtro_excluye_no_acero():
    for n in ["Ángulo Aluminio Blanco 32x32 mm 6 Metros para Acabados y Refuerzos",
              "Ángulo Café Decorativo 15x15 mm 3 Metros", "Ángulo Negro 15x15 mm Largo 6 Metros",
              "Viga pino Oregón cepillado 2 x 6 x 6 m", "Velador IPE Canela",
              "Conector viga acero/piso-cielo", "Clavos corrientes c x kg Uro",
              "5 CANALETAS 100x100MM CON REJILLA SUPERIOR ACERO GALVANIZADO",
              "Esquinero Para Cerámica Aluminio Cuadrado 10mm"]:
        assert not s.es_acero(n), n
    for n in ["Perfil Canal Acero 150x50x2mm 6 m", "Fierro A-63 10x10 mm 6 m",
              "Perfil Ángulo Acero 20x20x2 mm 2 m"]:
        assert s.es_acero(n), n


def test_muestra_real():
    filas = list(csv.DictReader(MUESTRA.open(encoding="utf-8")))
    acero = [f for f in filas if s.es_acero(f["nombre"])]
    assert len(filas) == 161
    assert len(acero) == 90  # 88 perfiles "Acero" + 2 fierros A-63
    for f in acero:
        c = s.clasificar(f["nombre"])
        assert c["tipo"] and c["dimensiones"] and c["largo_m"], f["nombre"]


def test_elegir_terminos():
    assert s.elegir_terminos("1") == s.TERMINOS[:1]
    assert s.elegir_terminos("pletina acero, barra lisa") == ["pletina acero", "barra lisa"]
    assert s.elegir_terminos(None) == s.TERMINOS
    assert "viga ipe" not in s.TERMINOS


def test_total_paginas():
    def html(pp):
        return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps({"props": {"pageProps": pp}})}</script>'
    assert s.total_paginas(html({"pagination": {"count": 95, "perPage": 48}})) == 2
    assert s.total_paginas(html({"pagination": {"totalPages": 4}})) == 4
    assert s.total_paginas(html({})) is None
    assert s.total_paginas("<html></html>") is None


def _c(nombre):
    c = s.clasificar(nombre)
    return (c["tipo"], c["dimensiones"], c["espesor_mm"], c["largo_m"])


def test_pletina_fierro_plano_y_barra_plana():
    assert _c("Fierro plano Acero 3x12 mm 6 m") == ("pletina", "3x12", 3.0, 6.0)
    assert _c("Fierro Plano Acero 5x100 mm 6 m") == ("pletina", "5x100", 5.0, 6.0)
    assert _c("Fierro Barra Plana Laminada en Caliente Acero 3x50 mm 6 m") == ("pletina", "3x50", 3.0, 6.0)


def test_tubo_redondo_pulgadas():
    assert _c('Perfil Tubular Redondo Acero 1 1/4" 2 mm 6 m') == ("tubo_redondo", '1 1/4"', 2.0, 6.0)
    assert _c('Perfil Tubular Redondo Acero 2" 1,5 mm 6 m') == ("tubo_redondo", '2"', 1.5, 6.0)
    assert _c('Perfil Tubular Redondo Acero 1" 2 mm 6 m') == ("tubo_redondo", '1"', 2.0, 6.0)


def test_barras_macizas():
    assert _c("Fierro Liso Redondo Acero 12x12 mm 6 m") == ("barra_redonda", "12", "", 6.0)
    assert _c("Fierro redondo Acero 22x22 mm 6 m") == ("barra_redonda", "22", "", 6.0)
    assert _c("Fierro Liso Cuadrado Acero 12x12 mm 6 m") == ("barra_cuadrada", "12", "", 6.0)
    assert _c("Fierro A-63 10x10 mm 6 m") == ("barra_a63", "10", "", 6.0)


def test_planchas():
    assert _c("Plancha negra laminado frio 3,0 x 1,0mt x 1,5mm") == ("plancha", "3000x1000", 1.5, 3.0)
    assert _c("Plancha negra laminado caliente 3,0 x 1,0mt x 4,0mm") == ("plancha", "3000x1000", 4.0, 3.0)
    assert _c("Plancha Acero Galvanizado 0.25x2 m 0.30 mm Galvanizado") == ("plancha", "2000x250", 0.3, 2.0)


def test_espesor_implausible():
    c = s.clasificar("Perfil Cuadrado Acero 25x25x15 mm 6 m")
    assert (c["dimensiones"], c["espesor_mm"]) == ("25x25x1.5", 1.5) and c["observacion"]
    assert s.clasificar("Perfil Cuadrado Acero 25x25x2 mm 6 m")["observacion"] == ""
    assert s.clasificar("Ángulo Laminado Acero 25x25x5 mm 6 m")["espesor_mm"] == 5.0


def test_reprocesar(tmp_path):
    ent = tmp_path / "v2.csv"
    viejos = ["fecha", "termino", "nombre", "sku", "precio_clp", "url",
              "tipo", "dimensiones", "espesor_mm", "largo_m", "proceso"]
    with ent.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=viejos)
        w.writeheader()
        w.writerow({"fecha": "2026-10-29", "termino": "pletina acero", "nombre": "Fierro Plano Acero 5x12 mm 6 m",
                    "sku": "1", "precio_clp": "100", "url": "u", "tipo": "redondo", "dimensiones": "5x12",
                    "espesor_mm": "", "largo_m": "6.0", "proceso": ""})
    sal = tmp_path / "v3.csv"
    s.main(["--reprocesar", str(ent), "--salida", str(sal)])
    filas = list(csv.DictReader(sal.open(encoding="utf-8")))
    assert list(filas[0]) == s.CAMPOS
    assert (filas[0]["tipo"], filas[0]["espesor_mm"], filas[0]["precio_clp"]) == ("pletina", "5.0", "100")
