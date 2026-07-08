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
    python scripts/retrofit/translate_descriptions.py --retry-empty   # recupera fallos de API
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import NamedTuple

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate, is_approved  # type: ignore

# Determinismo de langdetect: sin fijar la seed, el detector arranca de un estado
# aleatorio y el MISMO texto puede clasificarse distinto entre corridas (un item
# borderline detectado "es" un día y "it" al siguiente). Fijar la seed una vez, al
# importar el módulo, hace que toda llamada a detect() sea reproducible. El import
# va guardado para no romper el mensaje amigable de _require("langdetect") en main().
try:  # pragma: no cover - trivial guard
    from langdetect import DetectorFactory as _DetectorFactory  # type: ignore
    _DetectorFactory.seed = 0
except ImportError:  # pragma: no cover - _require() dará el error amigable en main()
    pass


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
# Botón de carrito italiano ("Aggiungi al Carrello" / la variante doble
# "Aggiungi Aggiungi al Carrello") + la cola de UI que le sigue. NO se compila
# con un ancla `$` + `.*` greedy suelto: eso asume que el junk va SIEMPRE al final
# y borra el contenido real cuando el botón aparece al PRINCIPIO — el caso de
# Funside Variant ("Sconto Aggiungi al carrello Confrontare <TÍTULO> Prezzo …"),
# que dejaba description_es="Descuento". El sub sólo lo aplica _strip_it_cart_suffix,
# que exige que el match sea una COLA real (ver abajo).
_IT_CART_SUFFIX = _re.compile(
    r'\s*(?:Aggiungi\s+)?Aggiungi al [Cc]arrello.*$',
    _re.IGNORECASE | _re.DOTALL,
)
# Ventana de "cola": sólo consideramos el botón como sufijo removible si arranca
# dentro de los últimos _IT_TAIL_WINDOW chars del texto.
_IT_TAIL_WINDOW = 150
# Contenido mínimo que debe quedar ANTES del botón para tratarlo como cola (evita
# nukear el cuerpo cuando el botón está casi al principio, p.ej. "Sconto Aggiungi…").
_IT_MIN_BODY_BEFORE = 40
# Prefijo de UI de Meian FR (~16 items): "EN SAVOIR PLUS"
_FR_JUNK_PREFIX = _re.compile(r'^EN SAVOIR PLUS\s*', _re.IGNORECASE)


def _strip_it_cart_suffix(text: str) -> str:
    """Remueve un bloque de botón "Aggiungi al Carrello…" SOLO si es cola real.

    Seguro contra la forma de listado de Funside Variant, donde el junk va al
    PRINCIPIO ("Sconto Aggiungi al carrello Confrontare <TÍTULO> …"): remover desde
    ahí se comería el título. Sólo cortamos cuando el match es una COLA genuina:
      1. arranca dentro de los últimos _IT_TAIL_WINDOW chars (junk al final), y
      2. queda contenido sustancial ANTES del match (nunca borramos el cuerpo).
    Si el match arranca temprano o casi no hay texto antes, se deja intacto (el
    prefijo lo maneja _IT_JUNK_PREFIX, o simplemente no es un botón de cola).
    """
    m = _IT_CART_SUFFIX.search(text)
    if not m:
        return text
    start = m.start()
    if start < len(text) - _IT_TAIL_WINDOW:
        return text  # el botón está temprano (junk de prefijo) → no es cola
    if len(text[:start].strip()) < _IT_MIN_BODY_BEFORE:
        return text  # casi nada antes del botón → no arriesgar el contenido
    return text[:start].rstrip()


def _clean_description_for_translation(text: str) -> str:
    """Elimina chrome de UI de la tienda antes de enviar a la API de traducción.

    No modifica el campo `description` original — sólo limpia la cadena
    en memoria para que la traducción resultante sea más limpia.
    Los prefijos/sufijos que limpiamos son artefactos del scraper (botones
    'Aggiungi al Carrello', 'EN SAVOIR PLUS') que no aportan contenido.
    """
    t = _IT_JUNK_PREFIX.sub("", text)
    t = _strip_it_cart_suffix(t)
    t = _FR_JUNK_PREFIX.sub("", t)
    return t.strip()


class TranslationError(Exception):
    """La traducción falló: excepción de la API o resultado vacío para input no vacío.

    Se distingue a propósito de "el original ya estaba en español" (skip legítimo).
    Un fallo NO debe escribir `description_es` — el item queda pendiente y el próximo
    run lo reintenta.
    """


# Status de translate_to_es (ver TranslationResult):
_ST_TRANSLATED = "translated"   # se tradujo → escribir description_es=<texto> + hash
_ST_ALREADY_ES = "already_es"   # ya era ES / sin contenido / no-op → description_es="" + hash
_ST_FAILED = "failed"           # falló la API → NO escribir la key (reintento futuro)


class TranslationResult(NamedTuple):
    status: str          # uno de _ST_*
    text: str            # texto traducido (sólo significativo si status==_ST_TRANSLATED)
    service: str         # servicio usado/fallido ("deepl" | "google" | "")
    error: str           # mensaje de error (sólo si status==_ST_FAILED)


def _normalize_ws(s: str) -> str:
    """Colapsa whitespace para comparar 'mismo texto' módulo espacios."""
    return " ".join(s.split())


def _translate_deepl(text: str, translator) -> str:
    """Traduce con DeepL. Lanza TranslationError si la API falla o devuelve vacío."""
    try:
        result = translator.translate_text(text, target_lang="ES")
        out = result.text or ""
    except Exception as exc:
        raise TranslationError(f"deepl: {exc}") from exc
    if not out.strip():
        raise TranslationError("deepl: resultado vacío para input no vacío")
    return out


def _translate_google(text: str) -> str:
    """Traduce con Google (deep-translator). Lanza TranslationError si falla/vacío."""
    from deep_translator import GoogleTranslator  # type: ignore
    try:
        result = GoogleTranslator(source="auto", target="es").translate(text)
    except Exception as exc:
        raise TranslationError(f"google: {exc}") from exc
    if not result or not result.strip():
        raise TranslationError("google: resultado vacío para input no vacío")
    return result


def translate_to_es(
    text: str,
    deepl_translator,  # puede ser None si no hay clave/paquete
    sleep_secs: float = 0.1,
) -> TranslationResult:
    """Traduce `text` al español y reporta el resultado como TranslationResult.

    Cuando DeepL está disponible (deepl_translator is not None) y el idioma
    está en _DEEPL_SOURCE_LANGS, se usa DeepL primero (mejor calidad). Si falla,
    cae a Google Translate (siempre disponible). Con deepl_translator None va
    directo a Google.

    Status devuelto:
    - _ST_ALREADY_ES  → el original ya es español, quedó vacío tras limpiar el
      chrome de UI, o la API devolvió texto idéntico al input (no-op). En todos
      estos casos description_es debe quedar "" (skip legítimo, NO gastar tokens).
    - _ST_TRANSLATED  → traducción real; `text` trae el resultado.
    - _ST_FAILED      → TODOS los servicios fallaron (excepción o vacío). NO se debe
      escribir description_es; `service`/`error` traen el último fallo para el log.
    """
    if not text or not text.strip():
        return TranslationResult(_ST_ALREADY_ES, "", "", "")

    # Limpiar chrome de UI de la tienda antes de detectar idioma y traducir
    cleaned = _clean_description_for_translation(text)
    if not cleaned:
        return TranslationResult(_ST_ALREADY_ES, "", "", "")

    from langdetect import detect, LangDetectException  # type: ignore

    try:
        lang = detect(cleaned)
    except LangDetectException:
        lang = "unknown"

    # Ya está en español — no hay nada que hacer (skip legítimo)
    if lang == "es":
        return TranslationResult(_ST_ALREADY_ES, "", "", "")

    last_service = ""
    last_error = ""

    # Ruta upgrade: DeepL (si disponible y lang soportado)
    if deepl_translator is not None and (lang in _DEEPL_SOURCE_LANGS or lang == "unknown"):
        try:
            with _deepl_lock:
                out = _translate_deepl(cleaned, deepl_translator)
            time.sleep(sleep_secs)
            if _normalize_ws(out) == _normalize_ws(cleaned):
                # No-op barato: la API devolvió el mismo texto → ya estaba en destino
                return TranslationResult(_ST_ALREADY_ES, "", "deepl", "")
            return TranslationResult(_ST_TRANSLATED, out, "deepl", "")
        except TranslationError as exc:
            last_service, last_error = "deepl", str(exc)
            # DeepL falló → fallback a Google

    # Ruta guaranteed: Google Translate (funciona siempre, sin API key)
    try:
        with _google_lock:
            out = _translate_google(cleaned)
        time.sleep(sleep_secs)
        if _normalize_ws(out) == _normalize_ws(cleaned):
            return TranslationResult(_ST_ALREADY_ES, "", "google", "")
        return TranslationResult(_ST_TRANSLATED, out, "google", "")
    except TranslationError as exc:
        last_service, last_error = "google", str(exc)

    # Todos los servicios disponibles fallaron → NO marcar como procesado
    return TranslationResult(_ST_FAILED, "", last_service, last_error)


# ---------------------------------------------------------------------------
# Lógica de item
# ---------------------------------------------------------------------------

def _description_src_hash(text: str) -> str:
    """Hash de staleness del `description` original (sha1 hex truncado a 12).

    Se persiste junto a `description_es` para que el merge del scraper (WO-A)
    pueda invalidar la traducción "sticky" cuando el original cambia: si el hash
    guardado no coincide con sha1(nuevo description), la traducción quedó stale y
    debe recomputarse. Nombre y formato de campo son un contrato con WO-A:
    `description_es_src_hash` = sha1(description).hexdigest()[:12].
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _field_not_spanish(desc: str) -> bool:
    """¿El `description` (ya limpio de chrome) NO detecta como español?

    Se usa para decidir si un `description_es=""` es un fallo de API mal marcado
    como "ya-ES" (candidato a --retry-empty) o un skip legítimo (original ES).
    Si tras limpiar el chrome no queda nada, NO es candidato (no hay qué salvar).
    """
    cleaned = _clean_description_for_translation(desc)
    if not cleaned:
        return False
    from langdetect import detect, LangDetectException  # type: ignore
    try:
        return detect(cleaned) != "es"
    except LangDetectException:
        return True  # idioma incierto → vale la pena reintentar


def _field_should_translate(container: dict, force: bool, retry_empty: bool) -> bool:
    """¿Este contenedor (item o extra) tiene su `description` pendiente de traducir?

    Usa presencia de la KEY como sentinel de "ya procesado":
    - `"description_es" not in container` → pendiente (nunca procesado).
    - key presente → procesado; se salta salvo:
        * --force (re-traduce todo), o
        * --retry-empty Y description_es=="" Y el original NO detecta como español
          (recupera fallos de API marcados por error como "ya-ES").
    """
    desc = container.get("description")
    if not desc:
        return False
    if force:
        return True
    if "description_es" not in container:
        return True
    if retry_empty and container.get("description_es") == "" and _field_not_spanish(desc):
        return True
    return False


def _needs_translation(item: dict, force: bool, retry_empty: bool = False) -> bool:
    """¿Tiene el item al menos un campo pendiente de traducción?

    Delega la decisión por-campo en `_field_should_translate` (misma lógica que usa
    `translate_item`, así la selección de pendientes y el trabajo real no divergen).
    """
    if _field_should_translate(item, force, retry_empty):
        return True
    for ex in item.get("extras") or []:
        if _field_should_translate(ex, force, retry_empty):
            return True
    return False


def translate_item(
    item: dict,
    deepl_translator,
    force: bool,
    sleep_secs: float,
    retry_empty: bool = False,
) -> tuple[dict, int, int, list[dict]]:
    """Traduce los campos traducibles del item.

    Retorna (item_actualizado, traducidos, ya_es, fallos) donde:
    - traducidos = campos con traducción real escrita.
    - ya_es      = campos marcados description_es="" (original ES / sin contenido / no-op).
    - fallos     = lista de {"field", "service", "error"} por cada campo que falló en
      TODOS los servicios. Un fallo NO escribe la key → el item queda pendiente y el
      próximo run lo reintenta (`description_es=""` queda RESERVADO para "ya era ES").

    Al escribir `description_es` (traducción o marca ya-ES "") se escribe también
    `description_es_src_hash` (staleness) sobre el mismo contenedor.
    """
    translated = 0
    already_es = 0
    failures: list[dict] = []
    result = dict(item)

    def _apply(container: dict, raw_desc: str, field_label: str) -> None:
        nonlocal translated, already_es
        tr = translate_to_es(raw_desc, deepl_translator, sleep_secs)
        if tr.status == _ST_FAILED:
            # NO escribir la key: el item queda pendiente para el próximo run.
            failures.append({"field": field_label, "service": tr.service, "error": tr.error})
            return
        # _ST_TRANSLATED → texto; _ST_ALREADY_ES → "" (ambos marcan "procesado")
        container["description_es"] = tr.text
        container["description_es_src_hash"] = _description_src_hash(raw_desc)
        if tr.status == _ST_TRANSLATED:
            translated += 1
        else:
            already_es += 1

    # description → description_es
    desc = item.get("description", "")
    if desc and _field_should_translate(item, force, retry_empty):
        _apply(result, desc, "description")

    # extras[].description → extras[].description_es
    extras = item.get("extras") or []
    if extras:
        new_extras = []
        for i, ex in enumerate(extras):
            ex_copy = dict(ex)
            ex_desc = ex.get("description", "")
            if ex_desc and _field_should_translate(ex, force, retry_empty):
                _apply(ex_copy, ex_desc, f"extras[{i}]")
            new_extras.append(ex_copy)
        result["extras"] = new_extras

    return result, translated, already_es, failures


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
    parser.add_argument("--include-approved", action="store_true",
                        help="Procesar también items aprobados (golden records). Por "
                             "defecto se saltean para no pisar metadata aprobada.")
    parser.add_argument("--retry-empty", action="store_true",
                        help="Reprocesa SOLO los campos con description_es=='' cuya "
                             "description NO detecta como español — recupera fallos de API "
                             "que quedaron marcados por error como 'ya-ES'. Respeta "
                             "--include-approved (default: NO toca aprobados). No re-traduce "
                             "los campos ya traducidos ni los que sí son español.")
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
    # Golden records: el owner aprobó esta card; no la re-traducimos. Queda
    # intacta en `updated_items` y se reescribe sin cambios.
    skipped_approved = sum(
        1 for item in items
        if "_raw" not in item and is_approved(item) and not args.include_approved
    )
    pending_idxs = [
        i for i, item in enumerate(items)
        if "_raw" not in item
        and not (is_approved(item) and not args.include_approved)
        and _needs_translation(item, args.force, args.retry_empty)
    ]
    if args.limit:
        pending_idxs = pending_idxs[: args.limit]
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados "
              f"(usa --include-approved para incluirlos).", flush=True)
    if args.retry_empty:
        print("[INFO] Modo --retry-empty: sólo campos description_es=='' cuya "
              "description no es español (recupera fallos de API).", flush=True)

    # Contar campos pendientes para estimación de carga (misma decisión por-campo
    # que translate_item, así el estimado no diverge del trabajo real).
    desc_pending = sum(
        1 for i in pending_idxs
        if _field_should_translate(items[i], args.force, args.retry_empty)
    )
    extras_pending = sum(
        sum(1 for ex in items[i].get("extras") or []
            if _field_should_translate(ex, args.force, args.retry_empty))
        for i in pending_idxs
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
    total_translated = 0   # campos con traducción real
    total_already_es = 0   # campos marcados description_es="" (ES / sin contenido / no-op)
    failed_slugs: list[str] = []  # items con ≥1 campo que falló en TODOS los servicios
    updated_items = list(items)
    done = 0
    last_flush_at = 0

    def process_idx(idx: int) -> tuple[int, dict, int, int, list[dict], bool]:
        item = items[idx]
        try:
            new_item, count, ae, failures = translate_item(
                item, deepl_translator, args.force, args.sleep, args.retry_empty
            )
            return idx, new_item, count, ae, failures, True
        except Exception as exc:
            # Error inesperado (bug, no fallo de API): el item queda intacto → se
            # reintenta el próximo run. Se reporta como fallo con el error crudo.
            failure = [{"field": "item", "service": "", "error": str(exc)}]
            return idx, item, 0, 0, failure, False

    print(
        f"[INFO] Procesando con {args.workers} workers, "
        f"guardando cada {args.flush_every} items…",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_idx, idx): idx for idx in pending_idxs}
        for fut in as_completed(futures):
            idx, new_item, count, ae, failures, ok = fut.result()
            updated_items[idx] = new_item
            total_translated += count
            total_already_es += ae
            if failures:
                slug = items[idx].get("slug") or items[idx].get("url") or "?"
                failed_slugs.append(slug)
                # Log por-fallo a stderr con slug + servicio + error (no sólo conteo).
                for f in failures:
                    print(
                        f"  [WARN] traducción falló — slug={slug} "
                        f"campo={f['field']} servicio={f['service'] or '?'}: {f['error']}",
                        file=sys.stderr, flush=True,
                    )
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

    # --- Resumen: traducidos / ya-ES / FALLIDOS separados ---
    print(
        f"\n[INFO] Listo. {total_translated} campos traducidos, "
        f"{total_already_es} ya-ES/sin-contenido, "
        f"{len(failed_slugs)} items con fallo de API (pendientes para el próximo run).",
        flush=True,
    )
    if failed_slugs:
        if len(failed_slugs) <= 20:
            print("[WARN] Items con fallo de API (se reintentarán):", flush=True)
            for slug in failed_slugs:
                print(f"    - {slug}", flush=True)
        else:
            print(
                f"[WARN] {len(failed_slugs)} items con fallo de API "
                f"(lista omitida por ser >20; ver los WARN de arriba en stderr).",
                flush=True,
            )
    print(f"[OK] Escrito {dst} ({len(updated_items)} líneas).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
