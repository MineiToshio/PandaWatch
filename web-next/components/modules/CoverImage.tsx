'use client'

import Image from 'next/image'
import { useState } from 'react'
import { BookOpen } from 'lucide-react'

type CoverImageProps = {
  imageLocal?: string
  imageUrl?: string
  alt: string
  fill?: boolean
  sizes?: string
  priority?: boolean
  className?: string
}

function Placeholder({ className }: { className?: string }) {
  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--ink-100)',
        color: 'var(--ink-400)',
        width: '100%',
        height: '100%',
      }}
    >
      <BookOpen size={32} strokeWidth={1.5} />
    </div>
  )
}

export function CoverImage({
  imageLocal,
  imageUrl,
  alt,
  fill = false,
  sizes,
  priority = false,
  className,
}: CoverImageProps) {
  // Espejo local: symlink `/images/...` por defecto; contra el bucket
  // (NEXT_PUBLIC_IMAGE_BASE_URL) en deploy. Cuando apunta al bucket, la src es
  // absoluta → cae al <img> remoto de abajo (next/image no optimiza hosts sin
  // allowlist), que es lo deseado. Sin la env, comportamiento actual intacto.
  const imageBase = process.env.NEXT_PUBLIC_IMAGE_BASE_URL?.replace(/\/$/, '')
  const localSrc = imageLocal
    ? (imageBase ? `${imageBase}/${imageLocal}` : `/images/${imageLocal}`)
    : null
  const initialSrc: string | null = localSrc ?? (imageUrl ?? null)

  const [src, setSrc] = useState<string | null>(initialSrc)

  if (!src) {
    return <Placeholder className={className} />
  }

  const isLocal = src.startsWith('/images/')

  if (isLocal) {
    return (
      <Image
        src={src}
        alt={alt}
        fill={fill}
        sizes={sizes}
        priority={priority}
        className={className}
        style={{ objectFit: 'cover' }}
        onError={() => setSrc(imageUrl ?? null)}
      />
    )
  }

  // Remote fallback — plain <img> to avoid remotePatterns config across ~270 domains.
  // lazy por defecto (consistente con next/image); eager sólo si priority (LCP).
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      className={className}
      loading={priority ? 'eager' : 'lazy'}
      decoding="async"
      style={
        fill
          ? { position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', display: 'block' }
          : { objectFit: 'cover', width: '100%', height: '100%' }
      }
      onError={() => setSrc(null)}
    />
  )
}

export default CoverImage
