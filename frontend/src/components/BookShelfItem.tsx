import type { LibraryEntry } from '../types'
import { BookCoverImage } from './BookCoverImage'

interface BookShelfItemProps {
  entry: LibraryEntry
}

export function BookShelfItem({ entry }: BookShelfItemProps) {
  const { book } = entry

  return (
    <button
      type="button"
      onClick={() => {
        // no-op for now — detail/ranking dialog wired up in a later step
      }}
      className="group flex flex-col items-center w-[127px] shrink-0 cursor-pointer"
    >
      <BookCoverImage
        coverUrl={book.cover_url}
        title={book.title}
        className="h-[190px] w-[127px] rounded-sm shadow-md group-hover:-translate-y-1 group-hover:shadow-lg transition-[transform,box-shadow]"
      />
      <div className="h-[68px] w-full pt-4 text-center overflow-hidden">
        <p className="text-xs font-medium text-neutral-900 line-clamp-2">{book.title}</p>
        <div className="flex items-center justify-center gap-1 mt-0.5">
          <p className="text-[10px] text-neutral-500 truncate">{book.author}</p>
          {entry.rating != null && (
            <span className="shrink-0 text-[10px] font-semibold text-amber-700">
              ★{entry.rating}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}
