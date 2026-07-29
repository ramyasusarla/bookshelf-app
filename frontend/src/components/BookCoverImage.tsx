import { useState } from 'react'

interface BookCoverImageProps {
  coverUrl: string | null
  title: string
  className?: string
  fallbackTextClassName?: string
}

export function BookCoverImage({
  coverUrl,
  title,
  className = '',
  fallbackTextClassName = 'text-xs',
}: BookCoverImageProps) {
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const showCover = coverUrl && !failed

  return (
    <div
      className={`overflow-hidden bg-neutral-200 ${showCover && !loaded ? 'animate-pulse' : ''} ${className}`}
    >
      {showCover ? (
        <img
          src={coverUrl}
          alt={`Cover of ${title}`}
          className={`w-full h-full object-cover transition-opacity duration-300 ${
            loaded ? 'opacity-100' : 'opacity-0'
          }`}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
      ) : (
        <div
          className={`w-full h-full flex items-center justify-center p-1 text-center text-neutral-500 ${fallbackTextClassName}`}
        >
          {title}
        </div>
      )}
    </div>
  )
}
