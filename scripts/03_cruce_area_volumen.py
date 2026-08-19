"""
03_cruce_area_volumen.py
------------------------
FASE 2 (inicio): cruzar la serie satelital de AREA con la serie de VOLUMEN
de CONAGUA, limpiar artefactos, y medir si existe la relacion area <-> volumen.

Entradas (en ../data/):
    - area_agua_las_adjuntas.csv   (satelite: fecha, area_km2, pct_visible, satelite)
    - conagua_las_adjuntas.csv     (CONAGUA:  fecha, almacenamiento_hm3, ...)

Salidas (en ../data/):
    - serie_area_limpia.csv        (area diaria depurada, 1 valor por fecha)
    - cruce_area_volumen.csv       (fechas con area y volumen emparejados)
    - fig_dispersion_area_volumen.png
    - fig_series_superpuestas.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

D = os.path.join(os.path.dirname(__file__), "..", "data")

# ---------------------------------------------------------------
# 1. CARGAR
# ---------------------------------------------------------------
sat = pd.read_csv(os.path.join(D, "area_agua_las_adjuntas.csv"))
con = pd.read_csv(os.path.join(D, "conagua_las_adjuntas.csv"))
sat["fecha"] = pd.to_datetime(sat["fecha"])
con["fecha"] = pd.to_datetime(con["fecha"])
print(f"Satelite crudo: {len(sat)} filas")

# ---------------------------------------------------------------
# 2. LIMPIEZA DE LA SERIE SATELITAL
#    Problema A: fechas duplicadas (la region cae en 2 escenas Landsat;
#                cada escena capta parte del vaso). Nos quedamos con el
#                AREA MAXIMA de cada fecha = la captura mas completa.
#    Problema B: valores absurdamente bajos (nubes/sombra sobre el agua
#                que pasaron el filtro). Los quitamos con un umbral fisico.
# ---------------------------------------------------------------
# A: un valor por fecha = el mayor (captura mas completa del embalse)
sat_dia = sat.groupby("fecha", as_index=False)["area_km2"].max()
print(f"Tras deduplicar por fecha (max): {len(sat_dia)} fechas")

# B: quitar artefactos de area muy baja. El area minima real del embalse
#    (sequia extrema 2024) rondo los ~60 km2. Todo lo <40 km2 es artefacto.
UMBRAL_ARTEFACTO = 40.0
n_antes = len(sat_dia)
artefactos = sat_dia[sat_dia["area_km2"] < UMBRAL_ARTEFACTO]
sat_dia = sat_dia[sat_dia["area_km2"] >= UMBRAL_ARTEFACTO].reset_index(drop=True)
print(f"Artefactos de area baja (<{UMBRAL_ARTEFACTO} km2) removidos: {n_antes-len(sat_dia)}")

sat_dia.to_csv(os.path.join(D, "serie_area_limpia.csv"), index=False)

# ---------------------------------------------------------------
# 3. EMPAREJAR CON CONAGUA (por fecha exacta)
# ---------------------------------------------------------------
cruce = pd.merge(sat_dia, con[["fecha", "almacenamiento_hm3", "pct_llenado"]],
                 on="fecha", how="inner").sort_values("fecha").reset_index(drop=True)
print(f"Fechas emparejadas satelite<->CONAGUA: {len(cruce)}")
cruce.to_csv(os.path.join(D, "cruce_area_volumen.csv"), index=False)

# ---------------------------------------------------------------
# 4. RELACION AREA -> VOLUMEN
# ---------------------------------------------------------------
x = cruce["area_km2"].values            # area (km2)
y = cruce["almacenamiento_hm3"].values  # volumen (hm3)

# correlacion
r = np.corrcoef(x, y)[0, 1]
print(f"\nCorrelacion de Pearson area vs volumen: r = {r:.3f}  (r^2 = {r**2:.3f})")

# ajuste polinomial grado 2 (el vaso se ensancha con la altura -> no lineal)
coef2 = np.polyfit(x, y, 2)
pol2 = np.poly1d(coef2)
y_hat = pol2(x)
resid = y - y_hat
rmse = np.sqrt(np.mean(resid**2))
mae = np.mean(np.abs(resid))
ss_res = np.sum(resid**2)
ss_tot = np.sum((y - y.mean())**2)
r2 = 1 - ss_res/ss_tot
print(f"Ajuste cuadratico  V(A) = {coef2[0]:.4f}A^2 + {coef2[1]:.3f}A + {coef2[2]:.1f}")
print(f"  R^2 = {r2:.3f} | RMSE = {rmse:.1f} hm3 | MAE = {mae:.1f} hm3")

# ---------------------------------------------------------------
# 5. GRAFICAS
# ---------------------------------------------------------------
# (a) dispersion area vs volumen + curva ajustada
fig, ax = plt.subplots(figsize=(8, 6))
sc = ax.scatter(x, y, c=cruce["fecha"].map(mdates.date2num), cmap="viridis",
                s=28, alpha=0.8, edgecolor="none")
xs = np.linspace(x.min(), x.max(), 200)
ax.plot(xs, pol2(xs), "r-", lw=2, label=f"Ajuste cuadratico (R²={r2:.3f})")
ax.set_xlabel("Area de agua satelital (km²)")
ax.set_ylabel("Volumen CONAGUA (hm³)")
ax.set_title("Relacion Area–Volumen — Presa Vicente Guerrero")
cb = plt.colorbar(sc, ax=ax); cb.set_label("Fecha")
loc = mdates.AutoDateLocator(); cb.ax.yaxis.set_major_locator(loc)
cb.ax.yaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.legend(); ax.grid(alpha=0.3)
plt.tight_layout(); plt.savefig(os.path.join(D, "fig_dispersion_area_volumen.png"), dpi=130)

# (b) series superpuestas en el tiempo (doble eje)
fig, ax1 = plt.subplots(figsize=(12, 5))
ax1.plot(con["fecha"], con["almacenamiento_hm3"], color="#08589e", lw=1,
         label="Volumen CONAGUA (hm³)")
ax1.set_ylabel("Volumen CONAGUA (hm³)", color="#08589e")
ax1.tick_params(axis="y", labelcolor="#08589e")
ax2 = ax1.twinx()
ax2.scatter(sat_dia["fecha"], sat_dia["area_km2"], s=14, color="#e34a33",
            alpha=0.7, label="Area satelital (km²)")
ax2.set_ylabel("Area satelital (km²)", color="#e34a33")
ax2.tick_params(axis="y", labelcolor="#e34a33")
ax1.set_title("Volumen (CONAGUA) vs Area de agua (Landsat) — 2013–2025")
ax1.xaxis.set_major_locator(mdates.YearLocator())
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax1.grid(alpha=0.3)
plt.tight_layout(); plt.savefig(os.path.join(D, "fig_series_superpuestas.png"), dpi=130)

print("\nListo. Revisa las figuras en la carpeta data/.")
