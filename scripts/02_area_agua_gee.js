/**********************************************************************
 * FASE 1 - Serie de area de agua de la presa Vicente Guerrero (Las Adjuntas)
 * Plataforma: Google Earth Engine  ->  Code Editor (JavaScript)
 *   https://code.earthengine.google.com/
 *
 * QUE HACE:
 *   1. Toma todas las imagenes Landsat 8 y 9 sobre la presa (2013 - hoy).
 *   2. Enmascara nubes y sombras de nube.
 *   3. Calcula el indice de agua MNDWI y clasifica cada pixel como agua/no-agua.
 *   4. Mide el area de agua (km2) en cada fecha.
 *   5. Grafica la serie y la exporta a tu Google Drive como CSV.
 *
 * COMO USARLO:
 *   - Copia TODO este archivo y pegalo en el Code Editor (borra lo que haya).
 *   - Presiona "Run".
 *   - Revisa el mapa: la capa azul debe cubrir el vaso de la presa.
 *   - Ajusta el rectangulo "region" si hace falta (ver comentario abajo).
 *   - Para bajar el CSV: pestana "Tasks" (derecha) -> "Run" en la tarea de export.
 **********************************************************************/

// ------------------------------------------------------------------
// 1. REGION DE ESTUDIO
//    Rectangulo que ENCIERRA el vaso de la presa. Ajustalo si al correr
//    ves que deja fuera parte del agua o incluye otros cuerpos de agua.
//    Centro de la presa: lon -98.6664, lat 23.9594
// ------------------------------------------------------------------
var region = ee.Geometry.Rectangle([-98.90, 23.80, -98.48, 24.15]);
Map.centerObject(region, 11);
Map.addLayer(region, {color: 'red'}, 'Region de estudio', false);

// Rango de fechas (Landsat 8 empieza en 2013; L9 en 2021)
var FECHA_INI = '2013-03-18';
var FECHA_FIN = '2025-08-18';

// ------------------------------------------------------------------
// 2. FUNCIONES DE PROCESAMIENTO
// ------------------------------------------------------------------

// Aplica factores de escala oficiales de Landsat Collection 2 Nivel 2
// para convertir los numeros crudos a reflectancia real (0 - 1).
function escalar(img) {
  var opticas = img.select('SR_B.').multiply(0.0000275).add(-0.2);
  return img.addBands(opticas, null, true);
}

// Enmascara nubes, sombras de nube, cirros y nieve usando la banda QA_PIXEL.
function quitarNubes(img) {
  var qa = img.select('QA_PIXEL');
  // bits: 1=dilatada, 2=cirro, 3=nube, 4=sombra de nube, 5=nieve
  var mascara = qa.bitwiseAnd(parseInt('111110', 2)).eq(0);
  return img.updateMask(mascara);
}

// Calcula MNDWI = (Verde - SWIR1) / (Verde + SWIR1).
// En Landsat 8/9: Verde = SR_B3, SWIR1 = SR_B6.
// El agua tiene MNDWI alto (positivo); suelo y vegetacion, negativo.
function agregarMNDWI(img) {
  var mndwi = img.normalizedDifference(['SR_B3', 'SR_B6']).rename('MNDWI');
  return img.addBands(mndwi);
}

// ------------------------------------------------------------------
// 3. COLECCION LANDSAT 8 + 9 (misma estructura de bandas)
// ------------------------------------------------------------------
var l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2');
var l9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2');

var coleccion = l8.merge(l9)
  .filterBounds(region)
  .filterDate(FECHA_INI, FECHA_FIN)
  .filter(ee.Filter.lt('CLOUD_COVER', 80))   // descarta imagenes muy nubladas
  .map(quitarNubes)
  .map(escalar)
  .map(agregarMNDWI);

print('Numero de imagenes encontradas:', coleccion.size());

// ------------------------------------------------------------------
// 4. MEDIR EL AREA DE AGUA EN CADA IMAGEN
// ------------------------------------------------------------------
var UMBRAL = 0.0;   // MNDWI > 0  => agua. Puedes ajustar (0.0 a 0.1).

function medirArea(img) {
  var agua = img.select('MNDWI').gt(UMBRAL);        // 1 = agua, 0 = no
  // area de cada pixel de agua (m2) -> sumar sobre la region
  var areaImg = agua.multiply(ee.Image.pixelArea());
  var stats = areaImg.reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: region,
    scale: 30,               // resolucion Landsat = 30 m
    maxPixels: 1e10,
    bestEffort: true
  });
  var area_m2 = ee.Number(stats.get('MNDWI'));
  // fraccion de la region que quedo visible (sin nube) - control de calidad
  var visibles = img.select('MNDWI').mask().multiply(ee.Image.pixelArea())
                    .reduceRegion({reducer: ee.Reducer.sum(), geometry: region,
                                   scale: 30, maxPixels: 1e10, bestEffort: true});
  var frac_visible = ee.Number(visibles.get('MNDWI'))
                       .divide(region.area()).multiply(100);
  return ee.Feature(null, {
    'fecha': img.date().format('YYYY-MM-dd'),
    'area_km2': area_m2.divide(1e6),
    'pct_visible': frac_visible,           // % de la region sin nube
    'satelite': img.get('SPACECRAFT_ID')
  });
}

var serie = ee.FeatureCollection(coleccion.map(medirArea))
  // nos quedamos solo con fechas donde se vio >70% de la region (poca nube)
  .filter(ee.Filter.gt('pct_visible', 70))
  .sort('fecha');

print('Imagenes con buena vista (>70% sin nube):', serie.size());

// ------------------------------------------------------------------
// 5. VISUALIZACION
// ------------------------------------------------------------------

// Grafica de la serie de area
var grafica = ui.Chart.feature.byFeature(serie, 'fecha', ['area_km2'])
  .setChartType('LineChart')
  .setOptions({
    title: 'Area de agua de la presa Vicente Guerrero (Landsat)',
    hAxis: {title: 'Fecha'},
    vAxis: {title: 'Area (km2)'},
    lineWidth: 1, pointSize: 3, legend: {position: 'none'}
  });
print(grafica);

// Mapa: una imagen reciente con su mascara de agua, para verificar visualmente
var ejemplo = coleccion.sort('system:time_start', false).first();
Map.addLayer(ejemplo, {bands: ['SR_B4','SR_B3','SR_B2'], min: 0, max: 0.3},
             'Color real (imagen reciente)');
Map.addLayer(ejemplo.select('MNDWI').gt(UMBRAL).selfMask(),
             {palette: ['00BFFF']}, 'Agua detectada (MNDWI)');

// ------------------------------------------------------------------
// 6. EXPORTAR A GOOGLE DRIVE (el CSV que usaremos en Python)
// ------------------------------------------------------------------
Export.table.toDrive({
  collection: serie,
  description: 'area_agua_las_adjuntas',
  folder: 'LasAdjuntas',
  fileNamePrefix: 'area_agua_las_adjuntas',
  fileFormat: 'CSV',
  selectors: ['fecha', 'area_km2', 'pct_visible', 'satelite']
});
// Tras correr, ve a la pestana "Tasks" (derecha) y presiona "Run"
// para generar el CSV en tu Google Drive, carpeta "LasAdjuntas".
