# Sandbox de precios SIPCO

Tiendas **virtuales** con precios **simulados** que SIPCO lee una vez por semana (HU-19) para comparar el mercado con
su valor interno por kilo (HU-08) y mostrar los precios por tienda de cada perfil (HU-20). Se publica en GitHub Pages.

En la versión 1.0 SIPCO no lee sitios de terceros: una tienda real solo se agrega con la licencia de su proveedor
(subproceso 3.2 del informe; Ley 21.459). Por eso las tiendas de aquí son ficticias.

## Datos base: `datos/precios_promedios_v.csv`

142 productos de acero (ángulos, canales, costaneras, perfiles cuadrados y rectangulares, pletinas, barras, tubos y
planchas) con un precio base en CLP con IVA. Por razones académicas, la base se armó con precios publicados reales
capturados el 29-10-2026 (`herramientas/scrapear_origen.py`), sin el SKU ni la URL de la tienda de origen. La «v» es
de virtual: desde ahí, todos los precios del Sandbox son simulados.

`designacion_icha` dice a qué perfil del catálogo ICHA corresponde cada producto (78 de 142), calculado por sección y
medidas. SIPCO no asocia por nombre: este dato solo sirve para cargar la tabla inicial de «Productos por tienda», que
después mantiene Ventas.

## Tiendas virtuales: `datos/tiendas.json`

| Tienda | Fuente | IVA | Precio | Vende |
|---|---|---|---|---|
| Aceros del Norte V | HTML (`index.html`) | con IVA | base ± 4 % | todo |
| Ferretería Pampa V | API (`api/precios.json`) | sin IVA (neto) | base × 0,97 ± 5 % | ~85 % |
| Metales del Desierto V | Archivo (`precios.csv`) | con IVA | base × 1,03 ± 3 % | ~70 % |

La variación semanal sale de una semilla (semana, tienda, producto): la misma semana da siempre los mismos precios,
así que SIPCO se prueba contra precios conocidos (`esperados.csv`, indicador D3). Cada tienda tiene su propio SKU.

## Generar y publicar

```bash
python generar.py --semana 2026-W45 --salida sitio          # una semana concreta
python generar.py --caida ferreteria-pampa-v                # esa tienda no publica: lectura parcial en SIPCO
python -m pytest tests
```

El workflow `.github/workflows/publicar.yml` publica en GitHub Pages **cada domingo a las 12:00 UTC** los precios de la
semana que empieza el lunes. También se corre a mano desde **Actions → Publicar Sandbox de precios → Run workflow**
(con semana y tiendas caídas opcionales): es el botón «Actualizar» del Sandbox. SIPCO no tiene botón manual (HU-19).

El sitio publicado contiene:

- `tiendas.json`: semana, tiendas, tipo de fuente, IVA y ruta de su fuente.
- `productos.csv`: SKU de cada tienda con su perfil ICHA, para `cargar_tiendas_sandbox` en SIPCO.
- `esperados.csv`: precio publicado y largo de cada producto, para verificar la lectura (D3).

Para activarlo: **Settings → Pages → Source: GitHub Actions**.
