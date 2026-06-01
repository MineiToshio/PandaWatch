'use client'

import { useState, useEffect, useMemo, useCallback } from 'react'
import Image from 'next/image'
import { ChevronLeft, ChevronRight, BookOpen, X } from 'lucide-react'
import type { ItemImage } from '@/lib/types'

const KIND_LABELS: Record<string, string> = {
  gallery:       'Galería',
  extra:         'Extra',
}

function kindLabelForIdx(img: ItemImage, idx: number): string {
  if (idx === 0) return 'Portada'
  return KIND_LABELS[img.kind] ?? img.kind ?? 'Galería'
}

function getInitialSrc(img: ItemImage): string | null {
  return img.local ? `/images/${img.local}` : (img.url || null)
}

// Deduplicate images by URL stem (strip query params).
// When two entries share the same base URL, keep the first's kind/description
// but borrow `local` from whichever has it (gallery sometimes has the
// downloaded file even when the cover entry doesn't).
function dedupeImages(images: ItemImage[]): ItemImage[] {
  const seen = new Map<string, ItemImage>()
  for (const img of images) {
    const key = (img.url || '').split('?')[0].split('#')[0]
    if (!key) continue
    if (!seen.has(key)) {
      seen.set(key, img)
    } else {
      const existing = seen.get(key)!
      if (!existing.local && img.local) {
        seen.set(key, { ...existing, local: img.local })
      }
    }
  }
  return Array.from(seen.values())
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
  const [src, setSrc] = useState<string | null>(
    images.length ? getInitialSrc(images[0]) : null
  )
  const [lightboxOpen, setLightboxOpen] = useState(false)

  const prev = useCallback(() => setIdx(i => (i - 1 + images.length) % images.length), [images.length])
  const next = useCallback(() => setIdx(i => (i + 1) % images.length), [images.length])

  // Sync src when navigating to a different image
  useEffect(() => {
    setSrc(images[idx] ? getInitialSrc(images[idx]) : null)
  }, [idx, images])

  // Keyboard: arrows + Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && lightboxOpen) { setLightboxOpen(false); return }
      if (images.length <= 1) return
      if (e.key === 'ArrowLeft') { if (lightboxOpen) e.preventDefault(); prev() }
      if (e.key === 'ArrowRight') { if (lightboxOpen) e.preventDefault(); next() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [images.length, lightboxOpen, prev, next])

  // Scroll lock while lightbox is open
  useEffect(() => {
    if (!lightboxOpen) return
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [lightboxOpen])

  const handleError = () => {
    const current = images[idx]
    if (src?.startsWith('/images/') && current?.url) setSrc(current.url)
    else setSrc(null)
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

  const current = images[idx]
  const isLocal = Boolean(src?.startsWith('/images/'))
  const kindLabel = kindLabelForIdx(current, idx)

  return (
    <>
      {/* ── Thumbnail carousel ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
        role="region" aria-label="Galería de imágenes">

        {/* Main image — click to open lightbox */}
        <div
          onClick={() => setLightboxOpen(true)}
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
                style={{ objectFit: 'contain' }}
                onError={handleError}
              />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={src}
                alt={`${alt} — ${kindLabel}`}
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
