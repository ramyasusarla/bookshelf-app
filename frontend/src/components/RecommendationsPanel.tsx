import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@clerk/clerk-react'
import { fetchRecommendations } from '../api'
import type { Category, Recommendation } from '../types'
import { CATEGORY_LABELS } from '../types'
import { BookCoverImage } from './BookCoverImage'
import { ALL_GENRES, type GenreFilterValue } from './GenreFilter'

interface RecommendationsPanelProps {
  genreFilter: GenreFilterValue
}

export function RecommendationsPanel({ genreFilter }: RecommendationsPanelProps) {
  const category = genreFilter === ALL_GENRES ? undefined : (genreFilter as Category)
  const { getToken } = useAuth()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['recommendations', genreFilter],
    queryFn: async () => fetchRecommendations(await getToken(), category),
  })

  return (
    <aside className="w-full lg:w-56 shrink-0">
      <h2 className="text-sm font-semibold text-neutral-900 mb-4">Recommended for You</h2>

      {isLoading && <p className="text-xs text-neutral-500">Loading recommendations…</p>}

      {isError && (
        <p className="text-xs text-red-600">
          Couldn't load recommendations:{' '}
          {error instanceof Error ? error.message : 'unknown error'}
        </p>
      )}

      {data && data.recommendations.length === 0 && (
        <p className="text-xs text-neutral-500">
          Rate at least one book 7 or higher {category ? `in ${CATEGORY_LABELS[category]}` : 'overall'} to
          get recommendations.
        </p>
      )}

      {data && data.recommendations.length > 0 && (
        <div className="flex flex-col gap-4">
          {data.recommendations.map((rec) => (
            <RecommendationCard key={rec.open_library_id} recommendation={rec} />
          ))}
        </div>
      )}
    </aside>
  )
}

function RecommendationCard({ recommendation }: { recommendation: Recommendation }) {
  return (
    <div className="flex gap-3 items-start">
      <BookCoverImage
        coverUrl={recommendation.cover_url}
        title={recommendation.title}
        className="h-24 w-16 shrink-0 rounded-sm shadow-sm"
        fallbackTextClassName="text-[9px]"
      />
      <div className="min-w-0">
        <p className="text-xs font-medium text-neutral-900 line-clamp-2">{recommendation.title}</p>
        <p className="text-[10px] text-neutral-500 line-clamp-1">{recommendation.author}</p>
      </div>
    </div>
  )
}
