"""
01_descargar_conagua_rapido.py
------------------------------
Version RAPIDA de la descarga. En lugar de pedir el reporte de las 210 presas
dia por dia (~6700 peticiones), usa el endpoint de la GRAFICA, que devuelve
la serie diaria de UNA presa en bloques de ~90 dias por llamada.

    GET https://sinav30.conagua.gob.mx:8080/SINA45/PresasG/porPeriodoRHA/{FECHA}/{NOMBRE_OFICIAL}
    -> lista de {dias, almacenamiento, namo, nombrepresa} para los ~90 dias
       que TERMINAN en {FECHA}.

Cubrimos 2007 -> 2025 retrocediendo de 90 en 90 dias: ~75 peticiones, segundos.

Salida: data/conagua_las_adjuntas.csv  con columnas:
    fecha, almacenamiento_hm3, namo_hm3, pct_llenado

Nota: este endpoint NO trae elevacion del agua ni NAME (solo volumen y NAMO).
El volumen (almacenamiento_hm3) es la variable objetivo del proyecto, asi que
esto es lo que importa. Si mas adelante necesitas la elevacion, se saca con el
script lento (01_descargar_conagua.py).

Uso:
    python 01_descargar_conagua_rapido.py

Requisitos:
    pip install requests
"""

import csv
import os
import time
from datetime import date, timedelta

import requests

# ----------------------------- Configuracion -----------------------------
NOMBRE_OFICIAL = "Vicente Guerrero, Tamps."   # nombre EXACTO que exige la API
FECHA_INICIO   = date(2007, 1, 1)
FECHA_FIN      = date(2025, 4, 23)            # ver /SINA45/fechaMonitoreo/ultimo
VENTANA_DIAS   = 85                           # <90 para garantizar traslape entre bloques

ROOT = "https://sinav30.conagua.gob.mx:8080/SINA45/PresasG/porPeriodoRHA/"
SALIDA = os.path.join(os.path.dirname(__file__), "..", "data", "conagua_las_adjuntas.csv")

PAUSA_SEG = 0.3
TIMEOUT = 30
REINTENTOS = 3

SESION = requests.Session()
SESION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
})
# ------------------------------------------------------------------------


def pedir_bloque(fecha_fin):
    """Serie de ~90 dias que termina en fecha_fin. Devuelve lista de dicts."""
    url = ROOT + fecha_fin.isoformat() + "/" + NOMBRE_OFICIAL
    for intento in range(1, REINTENTOS + 1):
        try:
            r = SESION.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                datos = r.json()
                return datos if isinstance(datos, list) else []
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 * intento)
    return []


def main():
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)

    registros = {}   # fecha (str) -> dict, deduplicado por fecha
    cursor = FECHA_FIN
    n_llamadas = 0

    print(f"Descargando serie de '{NOMBRE_OFICIAL}' en bloques de ~90 dias...")
    while cursor >= FECHA_INICIO:
        bloque = pedir_bloque(cursor)
        n_llamadas += 1
        nuevos = 0
        for row in bloque:
            f = row.get("dias")
            if not f or f in registros:
                continue
            almac = row.get("almacenamiento")
            namo = row.get("namo")
            pct = round(100 * almac / namo, 2) if (almac is not None and namo) else ""
            registros[f] = {
                "fecha": f,
                "almacenamiento_hm3": almac,
                "namo_hm3": namo,
                "pct_llenado": pct,
            }
            nuevos += 1
        print(f"  bloque termina {cursor}  -> {len(bloque)} filas, {nuevos} nuevas "
              f"(total {len(registros)})")
        cursor -= timedelta(days=VENTANA_DIAS)
        time.sleep(PAUSA_SEG)

    # Ordenar por fecha ascendente y filtrar al rango pedido
    filas = sorted(registros.values(), key=lambda d: d["fecha"])
    filas = [x for x in filas if FECHA_INICIO.isoformat() <= x["fecha"] <= FECHA_FIN.isoformat()]

    with open(SALIDA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fecha", "almacenamiento_hm3", "namo_hm3", "pct_llenado"])
        w.writeheader()
        w.writerows(filas)

    print(f"\nListo en {n_llamadas} peticiones.")
    print(f"Registros: {len(filas)}  ({filas[0]['fecha']} -> {filas[-1]['fecha']})")
    print(f"Archivo: {os.path.abspath(SALIDA)}")


if __name__ == "__main__":
    main()
