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

function CoverImageContent({
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
        style={{ objectFit: 'contain' }}
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
      // Muchas tiendas bloquean hotlinks por Referer (auditoría #15); sin
      // esto el fallback remoto fallaba más seguido de lo necesario.
      referrerPolicy="no-referrer"
      style={
        fill
          ? { position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', display: 'block' }
          : { objectFit: 'contain', width: '100%', height: '100%' }
      }
      onError={() => setSrc(null)}
    />
  )
}

export function CoverImage(props: CoverImageProps) {
  // A different product/source must not inherit the previous image's fallback
  // state when React reuses a card between filters or navigation.
  return <CoverImageContent key={JSON.stringify([props.imageLocal, props.imageUrl])} {...props} />
}

export default CoverImage
