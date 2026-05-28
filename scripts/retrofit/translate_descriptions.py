#!/usr/bin/env python3
"""translate_descriptions.py — traduce description y extras[].description al español.

Popula `description_es` y `extras[].description_es` en items.jsonl usando:
  - Google Translate via `deep-translator` (PRIMARIO: gratis, sin API key, sin límites).
  - DeepL Free API (OPCIONAL, mejor calidad): si DEEPL_API_KEY está en .env y hay
    créditos disponibles, se usa como upgrade de calidad sobre Google para los idiomas
    soportados (DE, FR, IT, JP/JA, EN, PT, ZH, KO y más).

Los campos originales (`description`, `extras[].description`) NO se modifican
— detect_signals() los sigue usando intactos para calcular signal_types.

Flush incremental: el progreso se guarda a disco cada --flush-every items (default 50).
Si el proceso es interrumpido, los items ya traducidos no se pierden — el próximo run
los detecta como completos (idempotente) y sólo procesa los pendientes.

Prerequisitos obligatorios:
    pip install deep-translator langdetect

Prerequisitos opcionales (mejora de calidad con DeepL):
    pip install deepl
    # En .env (o variable de entorno):
    DEEPL_API_KEY=tu-clave-deepl-free   ← deepl.com → "Get API key" (gratis, crédito único)

Uso:
    python scripts/retrofit/translate_descriptions.py --dry-run
    python scripts/retrofit/translate_descriptions.py --limit 50
    python scripts/retrofit/translate_descriptions.py
    python scripts/retrofit/translate_descriptions.py --force
    python scripts/retrofit/translate_descriptions.py --workers 4
    python scripts/retrofit/translate_descriptions.py --flush-every 100
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate  # type: ignore


# ---------------------------------------------------------------------------
# Dependencias — fallo temprano con mensaje claro (solo obligatorias)
# ---------------------------------------------------------------------------

def _require(import_name: str, pip_name: str | None = None) -> None:
    import importlib
    try:
        importlib.import_module(import_name)
    except ImportError:
        pkg = pip_name or import_name
        print(
            f"[ERROR] Falta el paquete '{pkg}'. Instalarlo con:\n"
            f"  pip install {pkg}",
            file=sys.stderr,
        )
        sys.exit(1)


def _try_import(import_name: str) -> bool:
    """Retorna True si el módulo está disponible, False si no (sin abortar)."""
    import importlib
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Idiomas
# ---------------------------------------------------------------------------

# Códigos ISO 639-1 que langdetect puede devolver y que DeepL Free soporta
# como idioma fuente. Todo lo demás va a Google como primary o fallback.
_DEEPL_SOURCE_LANGS: frozenset[str] = frozenset({
    "bg", "cs", "da", "de", "el", "en", "et", "fi", "fr",
    "hu", "id", "it", "ja", "ko", "lt", "lv", "nb", "nl", "pl",
    "pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk",
    "zh", "zh-cn", "zh-tw",
    # "es" excluido a propósito — ya es español, no se traduce
})


# ---------------------------------------------------------------------------
# Helpers de traducción (thread-safe via locks laxos para rate-limit)
# ---------------------------------------------------------------------------

_deepl_lock = threading.Lock()
_google_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Limpieza de junk pre-traducción (UI-chrome capturado por el scraper)
# ---------------------------------------------------------------------------

import re as _re

# Prefijos de UI de tiendas italianas (Panini IT, ~128 items)
_IT_JUNK_PREFIX = _re.compile(
    r'^(?:Aggiungi alla lista desideri\s*|Aggiungi al carrello Confrontare\s*)',
    _re.IGNORECASE,
)
# Sufijos de botones de carrito italianos
_IT_JUNK_SUFFIX = _re.compile(
    r'\s*Aggiungi\s+Aggiungi al Carrello.*$',
    _re.IGNORECASE | _re.DOTALL,
)
_IT_JUNK_SUFFIX2 = _re.compile(
    r'\s*Aggiungi al Carrello.*$',
    _re.IGNORECASE | _re.DOTALL,
)
# Prefijo de UI de Meian FR (~16 items): "EN SAVOIR PLUS"
_FR_JUNK_PREFIX = _re.compile(r'^EN SAVOIR PLUS\s*', _re.IGNORECASE)


def _clean_description_for_translation(text: str) -> str:
    """Elimina chrome de UI de la tienda antes de enviar a la API de traducción.

    No modifica el campo `description` original — sólo limpia la cadena
    en memoria para que la traducción resultante sea más limpia.
    Los prefijos/sufijos que limpiamos son artefactos del scraper (botones
    'Aggiungi al Carrello', 'EN SAVOIR PLUS') que no aportan contenido.
    """
    t = _IT_JUNK_PREFIX.sub("", text)
    t = _IT_JUNK_SUFFIX.sub("", t)
    t = _IT_JUNK_SUFFIX2.sub("", t)
    t = _FR_JUNK_PREFIX.sub("", t)
    return t.strip()


def _translate_deepl(text: str, translator) -> str:
    """Traduce con DeepL. Retorna "" si falla."""
    try:
        result = translator.translate_text(text, target_lang="ES")
        return result.text or ""
    except Exception:
        return ""


def _translate_google(text: str) -> str:
    """Traduce con Google Translate via deep-translator. Retorna "" si falla."""
    from deep_translator import GoogleTranslator  # type: ignore
    try:
        result = GoogleTranslator(source="auto", target="es").translate(text)
        return result or ""
    except Exception:
        return ""


def translate_to_es(
    text: str,
    deepl_translator,  # puede ser None si no hay clave/paquete
    sleep_secs: float = 0.1,
) -> str:
    """Traduce `text` al español.

    Cuando DeepL está disponible (deepl_translator is not None) y el idioma
    está en _DEEPL_SOURCE_LANGS, se usa DeepL primero (mejor calidad). Si falla
    o el idioma no está soportado, cae a Google Translate (siempre disponible).

    Cuando deepl_translator es None, va directo a Google Translate.

    Retorna "" si:
    - el texto está vacío
    - ya está en español
    - la traducción falló en todos los servicios disponibles
    """
    if not text or not text.strip():
        return ""

    # Limpiar chrome de UI de la tienda antes de detectar idioma y traducir
    text = _clean_description_for_translation(text)
    if not text:
        return ""

    from langdetect import detect, LangDetectException  # type: ignore

    try:
        lang = detect(text)
    except LangDetectException:
        lang = "unknown"

    # Ya está en español — no hay nada que hacer
    if lang == "es":
        return ""

    # Ruta upgrade: DeepL (si disponible y lang soportado)
    if deepl_translator is not None and (lang in _DEEPL_SOURCE_LANGS or lang == "unknown"):
        with _deepl_lock:
            result = _translate_deepl(text, deepl_translator)
        if result:
            time.sleep(sleep_secs)
            return result
        # DeepL falló → fallback a Google

    # Ruta guaranteed: Google Translate (funciona siempre, sin API key)
    with _google_lock:
        result = _translate_google(text)
    if result:
        time.sleep(sleep_secs)
    return result


# ---------------------------------------------------------------------------
# Lógica de item
# ---------------------------------------------------------------------------

def _needs_translation(item: dict, force: bool) -> bool:
    """¿Tiene el item al menos un campo pendiente de traducción?

    Usa presencia de la KEY (no el valor) como sentinel de "ya procesado".
    - `"description_es" not in item` → pendiente (nunca procesado).
    - `"description_es" in item` → procesado: puede ser texto traducido ("…")
      o string vacío ("") que indica "descripción original ya era español /
      sin contenido traducible". En ambos casos se salta salvo --force.

    Esto evita que items con descripciones ya en español queden eternamente
    en la cola de "pendientes" (el caso clásico: ListadoManga con metadatos
    "Norma · Kanzenban · Manga · Berserk 1" — langdetect → "es" → translate
    retorna "" → sin este fix, el item se re-procesa en cada corrida).
    """
    if item.get("description") and (force or "description_es" not in item):
        return True
    for ex in item.get("extras") or []:
        if ex.get("description") and (force or "description_es" not in ex):
            return True
    return False


def translate_item(
    item: dict,
    deepl_translator,
    force: bool,
    sleep_secs: float,
) -> tuple[dict, int]:
    """Traduce todos los campos traducibles del item.

    Retorna (item_actualizado, cantidad_de_campos_traducidos).
    Siempre escribe `description_es` (con el texto traducido o con "" si ya
    era español / sin contenido traducible) para marcar el campo como
    procesado y no re-procesarlo en corridas futuras.
    """
    translated = 0
    result = dict(item)

    # description → description_es
    desc = item.get("description", "")
    if desc and (force or "description_es" not in item):
        translated_text = translate_to_es(desc, deepl_translator, sleep_secs)
        # Siempre escribe la key — "" marca "procesado, sin traducción necesaria"
        result["description_es"] = translated_text
        if translated_text:
            translated += 1

    # extras[].description → extras[].description_es
    extras = item.get("extras") or []
    if extras:
        new_extras = []
        for ex in extras:
            ex_copy = dict(ex)
            ex_desc = ex.get("description", "")
            if ex_desc and (force or "description_es" not in ex):
                translated_text = translate_to_es(ex_desc, deepl_translator, sleep_secs)
                # Siempre escribe la key
                ex_copy["description_es"] = translated_text
                if translated_text:
                    translated += 1
            new_extras.append(ex_copy)
        result["extras"] = new_extras

    return result, translated


# ---------------------------------------------------------------------------
# Escritura incremental — sin backup extra, solo tmp+rename
# ---------------------------------------------------------------------------

def _write_items_atomic(items: list[dict], dst: Path) -> None:
    """Escribe todos los items a disco de forma atómica (tmp + rename).

    No crea backups — eso lo hace el caller una sola vez al inicio.
    Si el proceso muere durante el write, el tmp queda huérfano y dst
    intacto (la operación no es parcial).
    """
    out_lines: list[str] = []
    for item in items:
        if "_raw" in item:
            out_lines.append(item["_raw"])
        else:
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    tmp = dst.with_suffix(".jsonl.translate-tmp")
    tmp.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    tmp.replace(dst)  # atómico en el mismo filesystem


# ---------------------------------------------------------------------------
# Inicialización de DeepL (opcional)
# ---------------------------------------------------------------------------

def _load_deepl_key() -> str:
    """Lee DEEPL_API_KEY del entorno o del archivo .env. Retorna "" si no existe."""
    key = os.getenv("DEEPL_API_KEY", "")
    if key:
        return key
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPL_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    return ""


def _init_deepl(deepl_key: str):
    """Inicializa el translator de DeepL si la clave está disponible.

    Retorna el translator o None si:
    - No hay clave configurada.
    - El paquete 'deepl' no está instalado.
    - La clave no es válida o no hay créditos.
    """
    if not deepl_key:
        return None

    if not _try_import("deepl"):
        print(
            "[WARN] DEEPL_API_KEY encontrada pero el paquete 'deepl' no está instalado.\n"
            "       Para instalarlo: pip install deepl\n"
            "       Continuando solo con Google Translate.",
            flush=True,
        )
        return None

    import deepl as deepl_module  # type: ignore
    translator = deepl_module.Translator(deepl_key)
    try:
        usage = translator.get_usage()
        chars_used = usage.character.count if usage.character else "?"
        chars_limit = usage.character.limit if usage.character else "?"
        print(f"[INFO] DeepL disponible — crédito usado: {chars_used:,} / {chars_limit:,} chars.", flush=True)
        return translator
    except Exception as exc:
        print(f"[WARN] No se pudo conectar a DeepL ({exc}). Usando solo Google Translate.", flush=True)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl",
                        help="Archivo fuente (default: data/items.jsonl).")
    parser.add_argument("--output", default="data/items.jsonl",
                        help="Archivo destino (default: data/items.jsonl).")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe nada; muestra cuántos campos se traducirían.")
    parser.add_argument("--force", action="store_true",
                        help="Re-traduce aunque description_es ya esté poblado.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Procesar como máximo N items pendientes (0 = sin límite).")
    parser.add_argument("--workers", type=int, default=4,
                        help="Threads paralelos para las llamadas a la API (default 4).")
    parser.add_argument("--sleep", type=float, default=0.15,
                        help="Pausa en segundos entre llamadas a la API (default 0.15).")
    parser.add_argument("--flush-every", type=int, default=50,
                        help="Guardar al disco cada N items procesados (default 50). "
                             "Permite retomar sin perder progreso si el proceso se interrumpe.")
    args = parser.parse_args()

    # --- Verificar dependencias obligatorias ---
    _require("deep_translator", "deep-translator")
    _require("langdetect")

    # --- Inicializar DeepL (opcional, mejora de calidad) ---
    deepl_key = _load_deepl_key()
    deepl_translator = _init_deepl(deepl_key)

    if deepl_translator is None:
        print("[INFO] Modo traducción: Google Translate (gratuito, sin límites).", flush=True)
    else:
        print("[INFO] Modo traducción: DeepL (calidad superior) + Google Translate (fallback).", flush=True)

    # --- Cargar items ---
    src = Path(args.input)
    dst = Path(args.output)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr, flush=True)
        return 1

    raw_lines = src.read_text(encoding="utf-8").splitlines()
    items: list[dict] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"_raw": line})

    print(f"[INFO] {len(items)} items cargados desde {src}.", flush=True)

    # --- Filtrar pendientes ---
    pending_idxs = [
        i for i, item in enumerate(items)
        if "_raw" not in item and _needs_translation(item, args.force)
    ]
    if args.limit:
        pending_idxs = pending_idxs[: args.limit]

    # Contar campos pendientes para estimación de carga
    extras_pending = sum(
        sum(1 for ex in items[i].get("extras") or []
            if ex.get("description") and (args.force or not ex.get("description_es")))
        for i in pending_idxs
    )
    desc_pending = sum(
        1 for i in pending_idxs
        if items[i].get("description") and (args.force or not items[i].get("description_es"))
    )
    print(
        f"[INFO] Pendientes: {len(pending_idxs)} items "
        f"({desc_pending} description + {extras_pending} extras[].description).",
        flush=True,
    )

    if not pending_idxs:
        print("[OK] Nada que traducir.", flush=True)
        return 0

    if args.dry_run:
        print("\nMuestra de items pendientes (primeros 8):")
        for idx in pending_idxs[:8]:
            item = items[idx]
            print(f"  • [{item.get('source', '?')[:30]}] {item.get('title', '')[:60]}")
            if item.get("description"):
                print(f"    desc: {item['description'][:90]}")
        if len(pending_idxs) > 8:
            print(f"  ... y {len(pending_idxs) - 8} más.")
        print("\n[DRY-RUN] No se escribió nada.")
        return 0

    # --- Backup ÚNICO al inicio (antes de cualquier escritura) ---
    if dst.exists():
        backup = backup_and_rotate(dst, "translate")
        print(f"[OK] Backup guardado en {backup}", flush=True)

    # --- Traducir con flush incremental ---
    total_translated = 0
    total_failed = 0
    updated_items = list(items)
    done = 0
    last_flush_at = 0

    def process_idx(idx: int) -> tuple[int, dict, int, bool]:
        item = items[idx]
        try:
            new_item, count = translate_item(
                item, deepl_translator, args.force, args.sleep
            )
            return idx, new_item, count, True
        except Exception as exc:
            url = item.get("url", "?")[:70]
            print(f"  [WARN] Error en '{url}': {exc}", file=sys.stderr, flush=True)
            return idx, item, 0, False

    print(
        f"[INFO] Procesando con {args.workers} workers, "
        f"guardando cada {args.flush_every} items…",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_idx, idx): idx for idx in pending_idxs}
        for fut in as_completed(futures):
            idx, new_item, count, ok = fut.result()
            updated_items[idx] = new_item
            total_translated += count
            if not ok or count == 0:
                total_failed += 1
            done += 1

            # Flush incremental cada flush_every items completados
            if done - last_flush_at >= args.flush_every:
                _write_items_atomic(updated_items, dst)
                last_flush_at = done
                pct = done * 100 // len(pending_idxs)
                print(
                    f"  [{done}/{len(pending_idxs)}] ({pct}%) "
                    f"{total_translated} campos traducidos — guardado ✓",
                    flush=True,
                )
            elif done % 10 == 0:
                print(
                    f"  [{done}/{len(pending_idxs)}] {total_translated} campos…",
                    flush=True,
                )

    # --- Flush final (recoge los últimos items desde el último flush parcial) ---
    _write_items_atomic(updated_items, dst)

    print(
        f"\n[INFO] Listo. {total_translated} campos traducidos, "
        f"{total_failed} items sin traducción (ya en ES o error de API).",
        flush=True,
    )
    print(f"[OK] Escrito {dst} ({len(updated_items)} líneas).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
