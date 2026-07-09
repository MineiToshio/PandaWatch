'use client'

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import Image from 'next/image'
import { ChevronLeft, ChevronRight, BookOpen, X } from 'lucide-react'
import type { ItemImage } from '@/lib/types'
import { dedupeImages } from '@/lib/images'

const KIND_LABELS: Record<string, string> = {
  gallery:       'Galería',
  extra:         'Extra',
}

function kindLabelForIdx(img: ItemImage, idx: number): string {
  if (idx === 0) return 'Portada'
  return KIND_LABELS[img.kind] ?? img.kind ?? 'Galería'
}

function Placeholder() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      width: '100%', height: '100%',
      color: 'var(--ink-400)',
    }}>
      <BookOpen size={48} strokeWidth={1.5} />
    </div>
  )
}

const ARROW_BUTTON: React.CSSProperties = {
  background: 'rgba(0,0,0,0.5)', border: 'none', color: '#fff',
  borderRadius: '50%', width: 40, height: 40, cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  flexShrink: 0,
}

/**
 * Fila de dots. Target táctil 24×24 (WCAG 2.5.8 pide ≥24px — auditoría #22:
 * antes el botón ENTERO medía 8px, casi inusable en móvil); el punto visual
 * sigue siendo 8px, centrado dentro del padding invisible del botón.
 */
function DotsRow({
  count, active, onSelect, inactiveColor = 'var(--ink-200)', centered = true,
}: {
  count: number
  active: number
  onSelect: (i: number) => void
  inactiveColor?: string
  centered?: boolean
}) {
  return (
    <div style={{ display: 'flex', justifyContent: centered ? 'center' : undefined, gap: 2 }}>
      {Array.from({ length: count }, (_, i) => (
        <button
          key={i}
          onClick={() => onSelect(i)}
          aria-label={`Imagen ${i + 1}`}
          aria-current={i === active ? 'true' : 'false'}
          style={{
            width: 24, height: 24, padding: 0,
            border: 'none', background: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <span
            aria-hidden="true"
            style={{
              width: 8, height: 8, borderRadius: '50%',
              background: i === active ? 'var(--bamboo-500)' : inactiveColor,
              transition: 'background 0.15s',
            }}
          />
        </button>
      ))}
    </div>
  )
}

export function ImageCarousel({ images: rawImages, alt }: { images: ItemImage[]; alt: string }) {
  const images = useMemo(() => dedupeImages(rawImages), [rawImages])
  const [idx, setIdx] = useState(0)
  // src se DERIVA de idx + nivel de fallback por imagen (nada de estado espejo
  // sincronizado por efecto): 'remote' = el espejo local falló → usar url;
  // 'none' = nada cargó → placeholder.
  const [errored, setErrored] = useState<Record<number, 'remote' | 'none'>>({})
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const lightboxRef = useRef<HTMLDialogElement>(null)

  const prev = useCallback(() => setIdx(i => (i - 1 + images.length) % images.length), [images.length])
  const next = useCallback(() => setIdx(i => (i + 1) % images.length), [images.length])

  const fallbackLevel = errored[idx]
  const currentImg = images[idx]
  const src: string | null =
    !currentImg || fallbackLevel === 'none'
      ? null
      : fallbackLevel === 'remote'
        ? (currentImg.url || null)
        : currentImg.local
          ? `/images/${currentImg.local}`
          : (currentImg.url || null)

  // Teclado global SOLO con el lightbox abierto — sin esto, las flechas
  // cambiaban la imagen desde cualquier punto de la página. El carrusel
  // inline navega con onKeyDown cuando tiene foco.
  useEffect(() => {
    if (!lightboxOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (images.length <= 1) return
      if (e.key === 'ArrowLeft') { e.preventDefault(); prev() }
      if (e.key === 'ArrowRight') { e.preventDefault(); next() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [images.length, lightboxOpen, prev, next])

  // <dialog>.showModal() da focus trap + Escape + backdrop gratis (auditoría
  // #13) — antes el foco se escapaba del lightbox con Tab pese a
  // aria-modal="true", y el manejo de foco/scroll-lock era manual.
  useEffect(() => {
    const dlg = lightboxRef.current
    if (!dlg) return
    if (lightboxOpen && !dlg.open) dlg.showModal()
    if (!lightboxOpen && dlg.open) dlg.close()
  }, [lightboxOpen])

  function handleLightboxBackdropClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === lightboxRef.current) setLightboxOpen(false)
  }

  const handleError = () => {
    setErrored(prevErr => ({
      ...prevErr,
      [idx]: src?.startsWith('/images/') && currentImg?.url ? 'remote' : 'none',
    }))
  }

  if (!images.length) {
    return (
      <div style={{
        aspectRatio: '2/3', background: 'var(--ink-100)', borderRadius: 10,
        display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--ink-400)',
      }}>
        <BookOpen size={48} strokeWidth={1.5} />
      </div>
    )
  }

  const current = currentImg
  const isLocal = Boolean(src?.startsWith('/images/'))
  const kindLabel = kindLabelForIdx(current, idx)

  return (
    <>
      {/* ── Thumbnail carousel ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

        {/* Contenedor neutro (role="group", NO role="button"): antes las
            flechas prev/next eran <button> ANIDADOS dentro de un
            role="button" — interactivos anidados inválidos en ARIA
            (auditoría #9). Ahora el único control que envuelve la imagen es
            el <button> de abajo; las flechas son hermanas absolutas. */}
        <div
          role="group"
          aria-label="Galería de imágenes"
          onKeyDown={e => {
            if (e.key === 'ArrowLeft' && images.length > 1) { e.preventDefault(); prev() }
            else if (e.key === 'ArrowRight' && images.length > 1) { e.preventDefault(); next() }
          }}
          style={{
            position: 'relative', aspectRatio: '2/3',
            background: 'var(--ink-100)', borderRadius: 10, overflow: 'hidden',
          }}
        >
          {/* Único interactivo: envuelve SOLO la imagen */}
          <button
            type="button"
            onClick={() => setLightboxOpen(true)}
            aria-label="Ampliar imagen"
            style={{
              position: 'absolute', inset: 0, width: '100%', height: '100%',
              padding: 0, border: 'none', background: 'transparent',
              cursor: 'zoom-in', display: 'block',
            }}
          >
            {src ? (
              isLocal ? (
                <Image
                  src={src}
                  alt={`${alt} — ${kindLabel}`}
                  fill
                  // Es la imagen principal de la ficha (LCP) — eager, no lazy
                  priority
                  sizes="(max-width: 640px) 100vw, 280px"
                  style={{ objectFit: 'contain' }}
                  onError={handleError}
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={src}
                  alt={`${alt} — ${kindLabel}`}
                  decoding="async"
                  referrerPolicy="no-referrer"
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                  onError={handleError}
                />
              )
            ) : (
              <Placeholder />
            )}
          </button>

          {/* Kind badge — decorativo, no bloquea el botón */}
          <div style={{
            position: 'absolute', top: 8, left: 8,
            background: 'rgba(0,0,0,0.65)', color: '#fff',
            fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 4,
            backdropFilter: 'blur(4px)', pointerEvents: 'none',
          }}>
            {kindLabel}
          </div>

          {/* Flechas — hermanas del botón de imagen, NO anidadas (auditoría #9) */}
          {images.length > 1 && (
            <>
              <button
                onClick={prev}
                aria-label="Imagen anterior"
                style={{
                  position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)',
                  ...ARROW_BUTTON, width: 32, height: 32,
                }}
              >
                <ChevronLeft size={18} />
              </button>
              <button
                onClick={next}
                aria-label="Imagen siguiente"
                style={{
                  position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                  ...ARROW_BUTTON, width: 32, height: 32,
                }}
              >
                <ChevronRight size={18} />
              </button>
            </>
          )}
        </div>

        {/* Extra description */}
        {current.description && (
          <p style={{ fontSize: 12, textAlign: 'center', color: 'var(--color-text-secondary)', margin: 0 }}>
            {current.description}
          </p>
        )}

        {/* Dots indicator (2–8 images) */}
        {images.length > 1 && images.length <= 8 && (
          <DotsRow count={images.length} active={idx} onSelect={setIdx} />
        )}
      </div>

      {/* ── Lightbox modal — <dialog> nativo (auditoría #13) ── */}
      <dialog
        ref={lightboxRef}
        className="pw-lightbox-dialog"
        aria-label="Galería ampliada"
        onClose={() => setLightboxOpen(false)}
        onClick={handleLightboxBackdropClick}
      >
        {/* stopPropagation: un click DENTRO del contenido no debe burbujear
            al <dialog> y disparar el cierre por "click en backdrop". */}
        <div
          onClick={e => e.stopPropagation()}
          style={{ display: 'flex', alignItems: 'center', gap: 16, maxWidth: '96vw' }}
        >
          {/* Close button */}
          <button
            onClick={() => setLightboxOpen(false)}
            aria-label="Cerrar galería"
            style={{
              position: 'fixed', top: 16, right: 16,
              background: 'rgba(255,255,255,0.15)', border: 'none', color: '#fff',
              borderRadius: '50%', width: 40, height: 40, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              zIndex: 1,
            }}
          >
            <X size={20} />
          </button>

          {/* Prev arrow */}
          {images.length > 1 && (
            <button onClick={prev} aria-label="Imagen anterior" style={ARROW_BUTTON}>
              <ChevronLeft size={24} />
            </button>
          )}

          {/* Image + overlays */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <div style={{ position: 'relative', lineHeight: 0 }}>
              {src ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={src}
                  alt={`${alt} — ${kindLabel}`}
                  referrerPolicy="no-referrer"
                  style={{
                    display: 'block',
                    maxWidth: '80vw',
                    maxHeight: '75vh',
                    width: 'auto',
                    height: 'auto',
                    borderRadius: 6,
                  }}
                  onError={handleError}
                />
              ) : (
                <div style={{
                  width: 240, height: 360, background: 'var(--ink-100)', borderRadius: 6,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--ink-400)',
                }}>
                  <BookOpen size={48} strokeWidth={1.5} />
                </div>
              )}

              {/* Kind badge — bottom-left */}
              <div style={{
                position: 'absolute', bottom: 8, left: 8,
                background: 'rgba(0,0,0,0.65)', color: '#fff',
                fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 4,
                backdropFilter: 'blur(4px)',
              }}>
                {kindLabel}
              </div>

              {/* Counter — bottom-right */}
              {images.length > 1 && (
                <div style={{
                  position: 'absolute', bottom: 8, right: 8,
                  background: 'rgba(0,0,0,0.65)', color: '#fff',
                  fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 4,
                  backdropFilter: 'blur(4px)',
                }}>
                  {idx + 1} / {images.length}
                </div>
              )}
            </div>

            {/* Description */}
            {current.description && (
              <p style={{ color: 'rgba(255,255,255,0.75)', fontSize: 13, margin: 0, textAlign: 'center' }}>
                {current.description}
              </p>
            )}

            {/* Dots (2–8 images) */}
            {images.length > 1 && images.length <= 8 && (
              <DotsRow
                count={images.length}
                active={idx}
                onSelect={setIdx}
                inactiveColor="rgba(255,255,255,0.35)"
                centered={false}
              />
            )}
          </div>

          {/* Next arrow */}
          {images.length > 1 && (
            <button onClick={next} aria-label="Imagen siguiente" style={ARROW_BUTTON}>
              <ChevronRight size={24} />
            </button>
          )}
        </div>
      </dialog>
    </>
  )
}

export default ImageCarousel
