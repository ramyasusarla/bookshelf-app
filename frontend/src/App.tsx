import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { SignedIn, SignedOut, SignInButton, UserButton, useAuth } from '@clerk/clerk-react'
import { fetchLibrary } from './api'
import { AddBookDialog } from './components/AddBookDialog'
import { BookShelfItem } from './components/BookShelfItem'
import { ALL_GENRES, GenreFilter, type GenreFilterValue } from './components/GenreFilter'
import { RankingDialog } from './components/RankingDialog'
import { RecommendationsPanel } from './components/RecommendationsPanel'
import type { Category } from './types'
import { CATEGORY_LABELS } from './types'

function App() {
  return (
    <div className="min-h-screen bg-white py-10 px-4">
      <SignedOut>
        <div className="max-w-md mx-auto mt-24 text-center">
          <h1 className="text-2xl font-semibold text-neutral-900 mb-4">My Bookshelf</h1>
          <p className="text-neutral-500 mb-6">Sign in to see your library.</p>
          <SignInButton mode="modal">
            <button
              type="button"
              className="rounded-md bg-neutral-900 text-white text-sm font-medium py-2 px-6"
            >
              Sign in
            </button>
          </SignInButton>
        </div>
      </SignedOut>

      <SignedIn>
        <LibraryView />
      </SignedIn>
    </div>
  )
}

function LibraryView() {
  const { getToken } = useAuth()
  const [genreFilter, setGenreFilter] = useState<GenreFilterValue>(ALL_GENRES)
  const [isAddDialogOpen, setAddDialogOpen] = useState(false)
  const [rankingUserBookId, setRankingUserBookId] = useState<number | null>(null)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['library'],
    queryFn: async () => fetchLibrary(await getToken()),
  })

  const availableGenres = useMemo<Category[]>(() => {
    if (!data) return []
    const present = new Set<Category>()
    for (const entry of data) {
      if (entry.book.category) present.add(entry.book.category)
    }
    return Array.from(present).sort((a, b) => CATEGORY_LABELS[a].localeCompare(CATEGORY_LABELS[b]))
  }, [data])

  const filteredEntries = useMemo(() => {
    if (!data) return []
    const filtered =
      genreFilter === ALL_GENRES ? data : data.filter((entry) => entry.book.category === genreFilter)
    // rank_position increases with quality (1 = worst); best first means descending,
    // with unranked books (no position yet) pushed to the end.
    return [...filtered].sort((a, b) => {
      if (a.rank_position == null && b.rank_position == null) return 0
      if (a.rank_position == null) return 1
      if (b.rank_position == null) return -1
      return b.rank_position - a.rank_position
    })
  }, [data, genreFilter])

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-neutral-900">My Bookshelf</h1>
        <UserButton afterSignOutUrl="/" />
      </div>

      {isLoading && <p className="text-neutral-500">Loading your library…</p>}

      {isError && (
        <p className="text-red-600">
          Couldn't load your library: {error instanceof Error ? error.message : 'unknown error'}
        </p>
      )}

      {data && (
        <div className="flex flex-col lg:flex-row gap-8">
          <div className="flex-1 min-w-0">
            <div className="mb-6">
              <GenreFilter genres={availableGenres} value={genreFilter} onChange={setGenreFilter} />
            </div>

            {filteredEntries.length === 0 ? (
              <p className="text-neutral-500">No books in this genre yet.</p>
            ) : (
              <div className="p-4 rounded-lg">
                <div className="bookshelf-boards flex flex-wrap items-start gap-x-6 gap-y-10 pb-10">
                  {filteredEntries.map((entry) => (
                    <BookShelfItem key={entry.id} entry={entry} />
                  ))}
                </div>
              </div>
            )}
          </div>

          <RecommendationsPanel genreFilter={genreFilter} />
        </div>
      )}

      <button
        type="button"
        onClick={() => setAddDialogOpen(true)}
        className="fixed top-8 right-16 w-14 h-14 rounded-full bg-white border-2 border-[#c9a876] text-[#8b5e3c] text-3xl leading-none shadow-lg hover:bg-[#faf6ee] flex items-center justify-center"
        aria-label="Add a book"
      >
        +
      </button>

      <AddBookDialog
        open={isAddDialogOpen}
        onClose={() => setAddDialogOpen(false)}
        onAdded={(entry) => setRankingUserBookId(entry.id)}
      />

      <RankingDialog
        open={rankingUserBookId !== null}
        userBookId={rankingUserBookId}
        onClose={() => setRankingUserBookId(null)}
      />
    </div>
  )
}

export default App
