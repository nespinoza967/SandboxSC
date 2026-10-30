# Scraper de precios Sodimac (perfiles de acero)

Script independiente que busca perfiles y barras de acero en sodimac.cl (ángulos laminados y
plegados, canales, costaneras, perfiles cuadrados/rectangulares, pletinas, fierro redondo y
cuadrado, barra lisa, tubos, planchas, vigas, perfil T) y **agrega** cada ejecución a un CSV con:

`fecha, termino, nombre, sku, precio_clp, url, tipo, dimensiones, espesor_mm, largo_m, proceso, observacion`

- `tipo`: angulo/canal/costanera/cuadrado/rectangular/pletina/tubo_redondo/barra_redonda/
  barra_cuadrada/barra_a63/plancha/viga/perfil_t.
- `dimensiones`: en mm. Pletina (fierro plano / barra plana) `3x50` con `espesor_mm` = 3;
  tubo redondo = diámetro nominal en pulgadas (`1 1/4"`); barras macizas = diámetro o lado
  (`12`, sin espesor); planchas `3000x1000` (largo x ancho) con `largo_m` = 3.0.
- `proceso`: laminado/plegado si el nombre lo indica.
- `observacion`: avisos de corrección automática, p. ej. `25x25x15` (espesor implausible para
  un perfil de 25) se interpreta como 1,5 mm.

Si el CSV existente tiene otras columnas, se escribe en `<nombre>_v3.csv` para no mezclar formatos.

## Uso (Windows, Git Bash)

```bash
py -m pip install -r scripts/sodimac/requirements.txt
py scripts/sodimac/scrapear.py                      # todos los términos, hasta 5 páginas c/u
py scripts/sodimac/scrapear.py --terminos 2         # solo los 2 primeros términos
py scripts/sodimac/scrapear.py --terminos "pletina acero,barra lisa" --paginas 2
# re-parsear un CSV ya descargado (sin red) a un archivo nuevo:
py scripts/sodimac/scrapear.py --reprocesar scripts/sodimac/precios_sodimac_v2.csv --salida precios_sodimac_v3.csv
```

`--reprocesar` no hace ningún request: vuelve a clasificar la columna `nombre` con las reglas
actuales y conserva fecha, término, SKU, precio y URL. Sin `--salida` escribe `<csv>_reprocesado.csv`.

Al partir imprime los términos y una duración estimada; luego el avance por página.
Ejecución completa: 17 términos × hasta 5 páginas, tope 80 requests → máx. ~11–20 min
(normalmente menos, porque corta cuando una página no trae productos nuevos).

## Cómo funciona

- Lee y respeta `robots.txt`; si no se puede leer, no continúa.
- Mínimamente intrusivo: un request a la vez, pausa aleatoria de 8–15 s, tope de 80 requests
  por ejecución (`--max-requests`), y se detiene de inmediato ante cualquier error, 403/429,
  captcha o Akamai.
- Paginación con `&page=N`: avanza mientras haya productos nuevos, hasta `--paginas` (5) o el
  total de páginas informado en `__NEXT_DATA__` (`pageProps.pagination`), si existe.
- Deduplica por SKU dentro de la ejecución.
- Filtra solo acero: descarta aluminio, madera/pino, ángulos decorativos (blanco/negro/café),
  accesorios y productos no relacionados. `--sin-filtro` lo desactiva. El log muestra cuántos
  se excluyeron.
- En desarrollo usar `--cache` (guarda el HTML en `scripts/sodimac/.cache/`).
- Pruebas de parseo/filtro (con nombres reales de una ejecución): `py -m pytest scripts/sodimac/tests`

> Nota: la paginación y los nuevos términos no se han probado contra el sitio real (el entorno
> donde se escribió no tiene acceso a sodimac.cl).
