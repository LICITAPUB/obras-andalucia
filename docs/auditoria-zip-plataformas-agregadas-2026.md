# Auditoría del ZIP de Plataformas Agregadas 2026

**Fuente:** `PlataformasAgregadasSinMenores_2026.zip`  
**Última captura incluida:** 17/11/2026  
**Alcance:** únicamente el feed de Plataformas Agregadas Sin Menores incluido en el ZIP. No es una consulta en directo ni incluye por sí solo el feed de perfiles de contratante.

## Procesamiento

- 524 ficheros ATOM examinados.
- 243.546 elementos `entry`.
- 18.388 elementos `at:deleted-entry`.
- 18.388 comentarios de retirada con tipo `CERRADA`.
- 17.000 identificadores distintos en los avisos de retirada.
- 0 errores de lectura XML.
- Se consolidaron las versiones por identificador, conservando la entrada con `updated` más reciente.

## Criterios del Radar aplicados

- Tipo contractual `TypeCode=3` o algún CPV con prefijo `45`.
- Lugar real de ejecución en Andalucía, mediante NUTS provincial o ubicación de los lotes cuando permite identificar una sola provincia.
- Valor económico total superior a 1.000.000 €, siguiendo la prioridad actual del parser: `EstimatedOverallContractAmount`; si falta, suma de importes de lotes cuando todos están informados; después `TaxExclusiveAmount` o `TotalAmount`.
- No se infiere el municipio a partir del órgano contratante ni del título.
- No se filtra por estado.

## Resultado consolidado

**202 expedientes únicos** que cumplen los filtros.

### Por estado de la última entrada

| Estado CODICE | Expedientes |
|---|---:|
| RES | 156 |
| EV | 24 |
| ADJ | 13 |
| PUB | 9 |
| ANUL | 0 |

### Por provincia de ejecución

| Provincia | Expedientes |
|---|---:|
| Sevilla | 47 |
| Cádiz | 31 |
| Granada | 26 |
| Almería | 24 |
| Málaga | 21 |
| Jaén | 20 |
| Huelva | 18 |
| Córdoba | 15 |
| **Total** | **202** |

### Por clasificación

| Clasificación | Expedientes |
|---|---:|
| Obra confirmada (`TypeCode=3`) | 189 |
| Candidato por CPV de obras | 13 |
| **Total** | **202** |

## Avisos de retirada y anulaciones

Los 18.388 avisos de retirada del ZIP tienen `at:comment type="CERRADA"`; no aparece ningún aviso `ANULADA`. Ninguno de los 202 expedientes filtrados tiene un aviso de retirada asociado en este ZIP.

Por tanto, este conjunto no aporta expedientes anulados entre los 202 resultados, pero el Radar debe conservar y mostrar tanto `CERRADA` como `ANULADA` cuando aparezcan en las fuentes diarias. Un aviso de retirada no borra el expediente: se aplica solo si su `when` es posterior al `updated` de la última entrada conocida. Una entrada posterior prevalece sobre el aviso.

## Limitaciones conocidas

- El ZIP contiene únicamente el feed de Plataformas Agregadas Sin Menores, no la totalidad de PLACSP ni las fuentes municipales externas.
- En los 202 resultados no se ha acreditado un municipio de ejecución; el dato provincial sí está identificado. No se debe inventar un municipio.
- Los importes siguen la lógica económica vigente del Radar; la interpretación fiscal de algunos campos CODICE requiere mantener la auditoría técnica abierta.
- Este informe no importa ni modifica el histórico operativo. La integración en `data/obras.json` debe hacerse mediante el proceso de sincronización controlado, sin reiniciar los checkpoints.

## Actualización automática

El repositorio ya contiene `.github/workflows/actualizar.yml`, programado a las 05:30, 11:30, 17:30 y 23:30 UTC, que ejecuta `scripts/actualizar.py`, guarda los datos y checkpoint y publica GitHub Pages. La lógica nueva de tombstones se ha añadido al parser en la rama de desarrollo. Para que esa lógica entre en producción debe integrarse la rama en la rama por defecto mediante el procedimiento autorizado.
