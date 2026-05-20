# Manga Watch

Tracker personal para detectar mangas fisicos coleccionistas, ediciones especiales, variantes, box sets, artbooks y extras.

## Instalacion

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

En Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Uso

Desde la raiz del proyecto:

```bash
python manga_watch.py
```

Tambien puedes ejecutar directamente el script principal:

```bash
python scripts/manga_watch.py
```

## Salidas

- `data/state.json`: estado para no repetir hallazgos.
- `data/items.jsonl`: historial de hallazgos nuevos o cambiados.
- `reports/YYYY-MM-DD.md`: reporte diario en Markdown.

## Browser web

La UI está en `web/index.html` y por defecto lee los datos vía `fetch` de
`data/items.jsonl` — siempre muestra el estado actual sin rebuildear.

```bash
./web/serve.sh             # arranca http://localhost:8000/web/ y abre el browser
```

Si necesitás abrir el HTML directo con doble-click (sin servidor),
embebé la data en el HTML primero:

```bash
python scripts/build_web.py            # embebe data/items.jsonl en el HTML
python scripts/build_web.py --clear    # vuelve al modo fetch dinámico
```

## Comandos utiles

```bash
python manga_watch.py --list-sources
python manga_watch.py --source-classes official,retailer --min-score 30
python manga_watch.py --source-classes trusted_media,social --min-score 35
python manga_watch.py --countries Francia,Italia
python manga_watch.py --countries Japon
```

Nota: si tu terminal usa tildes correctamente, puedes usar `--countries Japón`. Si no, usa el nombre tal como aparece en `sources.yml` o filtra por source class.
