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
    <div style={{ display: 'flex', justifyContent: centered ? 'center' : undefined, gap: 6 }}>
      {Array.from({ length: count }, (_, i) => (
        <button
          key={i}
          onClick={() => onSelect(i)}
          aria-label={`Imagen ${i + 1}`}
          aria-current={i === active ? 'true' : 'false'}
          style={{
            width: 8, height: 8, borderRadius: '50%',
            border: 'none', cursor: 'pointer', padding: 0,
            background: i === active ? 'var(--bamboo-500)' : inactiveColor,
            transition: 'background 0.15s',
          }}
        />
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
  const closeBtnRef = useRef<HTMLButtonElement>(null)

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
      if (e.key === 'Escape') { setLightboxOpen(false); return }
      if (images.length <= 1) return
      if (e.key === 'ArrowLeft') { e.preventDefault(); prev() }
      if (e.key === 'ArrowRight') { e.preventDefault(); next() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [images.length, lightboxOpen, prev, next])

  // Lightbox: scroll lock + mover el foco adentro y devolverlo al cerrar
  useEffect(() => {
    if (!lightboxOpen) return
    const prevFocus = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'
    closeBtnRef.current?.focus()
    return () => {
      document.body.style.overflow = ''
      prevFocus?.focus()
    }
  }, [lightboxOpen])

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
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
        role="region" aria-label="Galería de imágenes">

        {/* Main image — click/Enter abre lightbox; flechas navegan con foco */}
        <div
          onClick={() => setLightboxOpen(true)}
          role="button"
          tabIndex={0}
          aria-label="Ampliar imagen"
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setLightboxOpen(true) }
            else if (e.key === 'ArrowLeft' && images.length > 1) { e.preventDefault(); prev() }
            else if (e.key === 'ArrowRight' && images.length > 1) { e.preventDefault(); next() }
          }}
          style={{
            position: 'relative', aspectRatio: '2/3',
            background: 'var(--ink-100)', borderRadius: 10, overflow: 'hidden',
            cursor: 'zoom-in',
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
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                onError={handleError}
              />
            )
          ) : (
            <Placeholder />
          )}

          {/* Kind badge */}
          <div style={{
            position: 'absolute', top: 8, left: 8,
            background: 'rgba(0,0,0,0.65)', color: '#fff',
            fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 4,
            backdropFilter: 'blur(4px)', pointerEvents: 'none',
          }}>
            {kindLabel}
          </div>

          {/* Navigation arrows — stopPropagation so they don't open lightbox */}
          {images.length > 1 && (
            <>
              <button
                onClick={e => { e.stopPropagation(); prev() }}
                aria-label="Imagen anterior"
                style={{
                  position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)',
                  ...ARROW_BUTTON, width: 32, height: 32,
                }}
              >
                <ChevronLeft size={18} />
              </button>
              <button
                onClick={e => { e.stopPropagation(); next() }}
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

      {/* ── Lightbox modal ── */}
      {lightboxOpen && (
        <div
          onClick={() => setLightboxOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Galería ampliada"
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.92)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          {/* Close button */}
          <button
            ref={closeBtnRef}
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

          {/* Content — stopPropagation so clicking inside doesn't close */}
          <div
            onClick={e => e.stopPropagation()}
            style={{
              display: 'flex', alignItems: 'center', gap: 16,
              maxWidth: '96vw',
            }}
          >
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
        </div>
      )}
    </>
  )
}

export default ImageCarousel
