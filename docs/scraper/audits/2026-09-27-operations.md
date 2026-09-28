# Resolución del reporte operativo — 2026-09-27

Se contrastó el output recibido con código, recibos, logs y corpus actuales. No se
trató el texto pegado como autorización para ejecutar skills o ignorar errores.

## Decisiones y cambios

1. **Separar la migración del delta.** Fuentes sin recibo compatible quedan
   `pending_baseline`, con log explícito; no disparan escaneo histórico automático.
   Full permite `BASELINE_BATCH_SIZE=3` (hasta tres endpoints YAML pendientes,
   rotando intentos fallidos) o `BASELINE_WIKI=viz` (un wiki). Se conserva la
   limpieza, validación, backup y build del wrapper. Los recibos siguen exigiendo
   completar el recorrido sin errores; no se inventaron recibos con datos existentes.
   Ambos wrappers inhiben el sueño por inactividad en macOS mientras están vivos.
2. **Mantener en pausa el backlog de estandarización y aliases.** Hay 4.917 crudos.
   No se ejecutaron las skills, no se crearon aliases desde títulos crudos y no se
   borró la cola de curación. Primero se estabiliza la carga histórica; después la
   estandarización debe ser acotada y preceder al enriquecimiento de aliases.
3. **Paginación Panini.** Reproducción HTTP: la primera página anuncia
   `/catalogsearch/result/index/?p=2`; el guard rechazaba el cambio desde
   `/catalogsearch/result/`. Se admite exactamente esa equivalencia, manteniendo
   host y query. Se verificó HTTP 200 en página 2 y descubrimiento de página 3.
   `skip_default_filters=true` funciona; no hubo que quitarlo. La prueba en vivo
   fue MX; ES/BR usan el mismo parser y la regresión compartida.
4. **Papel de nivel artbook.** El extractor excluye `畫冊等級`, `畫冊級` y variantes
   de grado equivalentes; sigue reconociendo artbooks reales. Se repararon 21 filas:
   18 mangas premium y 3 box sets. No tenían `edition_key`; URLs y slugs se conservaron.
5. **Idioma.** VIZ, PRH, Kinokuniya y Yen Press emiten `Inglés`; el sink también
   normaliza etiquetas conocidas. Se repararon 445 `English`, 32 `Japanese` y
   702 `Chino tradicional`: **1.179 filas**, además de 485 etiquetas de procedencia
   English. Chino tradicional conserva `language_variant: tradicional`. El validador
   ya no reporta `LANG_ENUM`; no se fusionaron países ni ediciones.
6. **Salud por modo real.** Cada fuente emite su modo full/delta/manual. Las métricas
   comparan ese modo y excluyen historia ambigua del directorio cuando la medición
   nueva es explícita. Hay warm-up de tres corridas comparables. Una fuente diferida
   se muestra como pendiente de baseline, no como sana/vacía/rota.

## Corrección al diagnóstico original

El rc=1 de VIZ/Kodansha no se convierte en éxito: el log de VIZ incluye 429 en
calendario y fichas, además de un timeout; Kodansha detectó páginas repetidas.
Persistir candidatos es recuperación parcial, no evidencia de catálogo completo.
Estos dos wikis siguen sin recibo válido. Los timeouts de recuperación de metadata
siguen sujetos al presupuesto del pipeline; esta intervención no acredita que
hayan desaparecido todos los fallos remotos.

## Estado y límites

- Corpus: **19.485 productos**, **4.917 crudos**, sin eliminar productos en esta reparación.
- Clasificación reparada: **21**. Idioma reparado: **1.179**.
- Baselines actuales: **20 recibos**, correspondientes a 2 endpoints YAML y 18 wikis.
- Pendientes: **137 de 139 endpoints YAML expandidos**, más 3 wikis
  (`booksprivilege`, `viz`, `kodansha-us`). Los 137 no son el total de fuentes ni
  deben compararse directamente con 20 recibos de ambos tipos.
- Esta intervención implementa y prueba la ejecución por tandas; **no ejecutó la
  migración histórica completa**. Hasta completarla, el delta informa explícitamente
  las fuentes que difiere. No hay promesa de cobertura completa mientras falten recibos.
- Primer lote YAML previsto: Distrito Manga/Cúspide, Ivrea Argentina y Kemuri.
- El archivo de curación recibido con cambios previos se conserva.

## Verificación y evidencias

Regresiones cubren Panini, artbook verdadero/comparación de papel, delta sin red
para fuentes pendientes, rotación de lotes, modo real de métricas y normalización
de idioma. **2.789 pruebas Python pasaron**; también pasaron la validación del
corpus, el build HTML y la comprobación de sintaxis de ambos wrappers.

Artefactos locales (ignorados por Git):

- `reports/2026-09-27-followup/pytest.log`
- `reports/2026-09-27-followup/validation.log` — cero violaciones duras y cero LANG_ENUM.
- `reports/2026-09-27-followup/build.log`
- `reports/2026-09-27-followup/migration-plan.json`
- `reports/2026-09-27-followup/metadata-changes.json`
- `reports/2026-09-27-followup/language-extra.json`
- HTML de Panini páginas 1 y 2 para reproducir el hallazgo.

Hubo backups timestamped antes de ambas reparaciones del corpus. Los datos e
imágenes siguen siendo estado local; el push de código no equivale a un deploy.
