import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addToLibrary, searchBooks } from '../api'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import type { BookSearchResult, Category, LibraryEntry } from '../types'
import { CATEGORY_LABELS } from '../types'
import { BookCoverImage } from './BookCoverImage'

const CATEGORY_OPTIONS = Object.keys(CATEGORY_LABELS) as Category[]

interface AddBookDialogProps {
  open: boolean
  onClose: () => void
  onAdded: (entry: LibraryEntry) => void
}

export function AddBookDialog({ open, onClose, onAdded }: AddBookDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const queryClient = useQueryClient()

  const [searchTerm, setSearchTerm] = useState('')
  const debouncedSearchTerm = useDebouncedValue(searchTerm, 150)

  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('')
  const [category, setCategory] = useState<Category | ''>('')
  const [selected, setSelected] = useState<BookSearchResult | null>(null)

  const searchQuery = useQuery({
    queryKey: ['book-search', debouncedSearchTerm],
    queryFn: () => searchBooks(debouncedSearchTerm),
    enabled: debouncedSearchTerm.trim().length > 0,
  })

  const addMutation = useMutation({
    mutationFn: addToLibrary,
    onSuccess: (entry) => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
      onAdded(entry)
      dialogRef.current?.close()
    },
  })

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  function resetForm() {
    setSearchTerm('')
    setTitle('')
    setAuthor('')
    setCategory('')
    setSelected(null)
    addMutation.reset()
  }

  function handleDialogClose() {
    resetForm()
    onClose()
  }

  function handleBackdropClick(e: MouseEvent<HTMLDialogElement>) {
    if (e.target === dialogRef.current) dialogRef.current?.close()
  }

  function handleSelectResult(result: BookSearchResult) {
    setSelected(result)
    setTitle(result.title)
    setAuthor(result.author)
    setSearchTerm('')
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!title.trim() || !author.trim() || !category) return
    addMutation.mutate({
      title: title.trim(),
      author: author.trim(),
      cover_url: selected?.cover_url ?? null,
      description: selected?.description ?? null,
      open_library_id: selected?.open_library_id ?? null,
      category,
    })
  }

  const canSubmit =
    title.trim().length > 0 && author.trim().length > 0 && category !== '' && !addMutation.isPending
  const trimmedSearch = debouncedSearchTerm.trim()
  const hasResults = (searchQuery.data?.length ?? 0) > 0

  return (
    <dialog
      ref={dialogRef}
      onClose={handleDialogClose}
      onClick={handleBackdropClick}
      className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 backdrop:bg-black/40 rounded-xl p-0 w-full max-w-md m-0"
    >
      <div className="p-6">
        <form onSubmit={handleSubmit}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-neutral-900">Add a Book</h2>
            <button
              type="button"
              onClick={() => dialogRef.current?.close()}
              className="text-neutral-400 hover:text-neutral-600"
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          <label className="block text-sm font-medium text-neutral-700 mb-1">
            Search Open Library
          </label>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by title…"
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-neutral-900"
          />

          {searchQuery.isFetching && <p className="text-xs text-neutral-400 mb-2">Searching…</p>}

          {hasResults && (
            <ul className="mb-4 max-h-48 overflow-y-auto border border-neutral-200 rounded-md divide-y divide-neutral-100">
              {searchQuery.data!.map((result, i) => (
                <li key={`${result.open_library_id ?? result.title}-${i}`}>
                  <button
                    type="button"
                    onClick={() => handleSelectResult(result)}
                    className="w-full flex items-center gap-3 p-2 text-left hover:bg-neutral-50"
                  >
                    <BookCoverImage
                      coverUrl={result.cover_url}
                      title={result.title}
                      className="w-8 h-12 shrink-0 rounded-sm"
                      fallbackTextClassName="text-[7px]"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-neutral-900 truncate">{result.title}</p>
                      <p className="text-xs text-neutral-500 truncate">{result.author}</p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {trimmedSearch.length > 0 && !searchQuery.isFetching && !hasResults && (
            <p className="text-xs text-neutral-400 mb-4">
              No results — you can enter details manually below.
            </p>
          )}

          {selected && (
            <div className="flex items-center gap-3 p-2 mb-4 rounded-md border border-neutral-200 bg-neutral-50">
              <BookCoverImage
                coverUrl={selected.cover_url}
                title={selected.title}
                className="w-8 h-12 shrink-0 rounded-sm"
                fallbackTextClassName="text-[7px]"
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-neutral-900 truncate">{selected.title}</p>
                <p className="text-xs text-neutral-500 truncate">{selected.author}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="text-xs text-neutral-500 hover:text-neutral-700 underline shrink-0"
              >
                Clear
              </button>
            </div>
          )}

          <label className="block text-sm font-medium text-neutral-700 mb-1">Title</label>
          <input
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-neutral-900"
          />

          <label className="block text-sm font-medium text-neutral-700 mb-1">Author</label>
          <input
            type="text"
            required
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-neutral-900"
          />

          <label className="block text-sm font-medium text-neutral-700 mb-1">Genre</label>
          <select
            required
            value={category}
            onChange={(e) => setCategory(e.target.value as Category)}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm mb-4 bg-white focus:outline-none focus:ring-2 focus:ring-neutral-900"
          >
            <option value="" disabled>
              Select a genre…
            </option>
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>

          {addMutation.isError && (
            <p className="text-xs text-red-600 mb-3">
              Couldn't add this book:{' '}
              {addMutation.error instanceof Error ? addMutation.error.message : 'unknown error'}
            </p>
          )}

          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full rounded-md bg-neutral-900 text-white text-sm font-medium py-2 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {addMutation.isPending ? 'Adding…' : 'Add'}
          </button>
        </form>
      </div>
    </dialog>
  )
}
