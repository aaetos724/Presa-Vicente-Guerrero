"""
01_descargar_conagua.py
------------------------
Descarga la serie histórica diaria de almacenamiento de la presa
Vicente Guerrero / Las Adjuntas (clave SIH: VGRTP) desde el SINA de CONAGUA.

Fuente (API interna del portal de Monitoreo de Presas):
    GET https://sinav30.conagua.gob.mx:8080/PresasPG/presas/reporte/{AAAA-MM-DD}
    -> devuelve un JSON con ~210 presas para esa fecha.

Estrategia:
    - Recorremos día por día desde FECHA_INICIO hasta FECHA_FIN.
    - De cada respuesta nos quedamos solo con la fila de clave VGRTP.
    - Guardamos en CSV. El script es REANUDABLE: si se corta, al volver a
      correrlo continúa desde la última fecha guardada (no re-descarga).

Uso:
    python 01_descargar_conagua.py

Requisitos:
    pip install requests
"""

import csv
import os
import time
from datetime import date, timedelta

import requests

# ----------------------------- Configuración -----------------------------
CLAVE_SIH   = "VGRTP"                 # Vicente Guerrero / Las Adjuntas, Tamaulipas
FECHA_INICIO = date(2007, 1, 1)       # primer dato disponible en el SINA
FECHA_FIN    = date(2025, 4, 23)      # ultimo dato disponible (ver /SINA45/fechaMonitoreo/ultimo)
PASO_DIAS    = 1                      # 1 = diario | 7 = semanal (mas rapido, menos puntos)

BASE_URL = "https://sinav30.conagua.gob.mx:8080/PresasPG/presas/reporte/"
SALIDA   = os.path.join(os.path.dirname(__file__), "..", "data", "conagua_las_adjuntas.csv")

PAUSA_SEG = 0.25   # pausa entre peticiones (cortesia con el servidor)
TIMEOUT   = 30
REINTENTOS = 3

# El servidor esta detras de un WAF (Incapsula) que bloquea el User-Agent
# por defecto de python-requests. Nos identificamos como navegador.
SESION = requests.Session()
SESION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
})

# Columnas que guardamos (las relevantes del JSON del SINA)
CAMPOS = [
    "fechamonitoreo",     # fecha del registro
    "almacenaactual",     # <-- VARIABLE OBJETIVO: volumen almacenado (hm3)
    "elevacionactual",    # nivel del agua (msnm)
    "llenano",            # fraccion de llenado (0-1) respecto a NAMO
    "namoalmac",          # capacidad NAMO (hm3) - constante de referencia
    "nameelev", "namealmac", "namoelev",
]
# ------------------------------------------------------------------------


def fechas(inicio, fin, paso):
    d = inicio
    while d <= fin:
        yield d
        d += timedelta(days=paso)


def ultima_fecha_guardada(ruta):
    """Devuelve la ultima fecha ya presente en el CSV, o None si no existe."""
    if not os.path.exists(ruta):
        return None
    ultima = None
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            ultima = fila.get("fechamonitoreo") or ultima
    if ultima:
        y, m, d = map(int, ultima.split("-"))
        return date(y, m, d)
    return None


def pedir_reporte(fecha_str):
    """Pide el reporte de una fecha; devuelve la fila de nuestra presa o None."""
    url = BASE_URL + fecha_str
    for intento in range(1, REINTENTOS + 1):
        try:
            r = SESION.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                return None
            datos = r.json()
            if not isinstance(datos, list):
                return None
            for presa in datos:
                if presa.get("clavesih") == CLAVE_SIH:
                    return presa
            return None  # esa fecha existe pero sin nuestra presa
        except (requests.RequestException, ValueError):
            if intento == REINTENTOS:
                return None
            time.sleep(1.5 * intento)
    return None


def main():
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)

    inicio = FECHA_INICIO
    ultima = ultima_fecha_guardada(SALIDA)
    modo = "w"
    if ultima is not None:
        inicio = ultima + timedelta(days=PASO_DIAS)
        modo = "a"
        print(f"Reanudando: ultimo dato = {ultima}, continuo desde {inicio}")

    if inicio > FECHA_FIN:
        print("Nada que descargar: el CSV ya esta al dia.")
        return

    total = (FECHA_FIN - inicio).days // PASO_DIAS + 1
    print(f"Descargando {total} fechas ({inicio} -> {FECHA_FIN}, paso {PASO_DIAS}d)...")

    with open(SALIDA, modo, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
        if modo == "w":
            writer.writeheader()

        guardadas = faltantes = 0
        for i, d in enumerate(fechas(inicio, FECHA_FIN, PASO_DIAS), 1):
            fstr = d.isoformat()
            fila = pedir_reporte(fstr)
            if fila:
                writer.writerow(fila)
                guardadas += 1
            else:
                faltantes += 1
            if i % 50 == 0:
                f.flush()
                print(f"  {i}/{total}  ({fstr})  guardadas={guardadas} faltantes={faltantes}")
            time.sleep(PAUSA_SEG)

    print(f"\nListo. Guardadas={guardadas}, faltantes={faltantes}")
    print(f"Archivo: {os.path.abspath(SALIDA)}")


if __name__ == "__main__":
    main()
