# LICITAPUB

Radar de licitaciones públicas de obras en Andalucía.

## Instalación en GitHub

1. Sube **todo el contenido** de esta carpeta a la raíz del repositorio `licitapub`, conservando las rutas.
2. En Settings → Pages → Build and deployment, selecciona **GitHub Actions**.
3. En Actions, ejecuta manualmente `LICITAPUB - actualizar y publicar` con **Run workflow**.

## Contenido

- `index.html`: interfaz web. Mantiene la imagen corporativa GUAMAR y muestra LICITAPUB como nombre de la aplicación en la pestaña.
- `data/obras.json`: datos iniciales existentes, filtrados a importes sin IVA superiores a 1.000.000 €.
- `scripts/actualizar.py`: descarga PLACSP por lotes y guarda el cursor para reanudar.
- `scripts/enriquecer.py`: análisis de documentación PDF.
- `.github/workflows/actualizar.yml`: automatización y publicación en GitHub Pages.

La descarga histórica inicial no se considera completa hasta finalizar ambos feeds. Hasta entonces, el workflow guarda los lotes y el checkpoint, sin publicar una base incompleta. El código se ha validado sintácticamente; la conexión real con PLACSP debe verificarse en la primera ejecución de Actions.

No borres el repositorio anterior hasta comprobar que LICITAPUB funciona correctamente.
