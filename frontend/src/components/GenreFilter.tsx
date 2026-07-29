import type { Category } from '../types'
import { CATEGORY_LABELS } from '../types'

export const ALL_GENRES = 'all' as const
export type GenreFilterValue = Category | typeof ALL_GENRES

interface GenreFilterProps {
  genres: Category[]
  value: GenreFilterValue
  onChange: (value: GenreFilterValue) => void
}

export function GenreFilter({ genres, value, onChange }: GenreFilterProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <FilterPill label="All" active={value === ALL_GENRES} onClick={() => onChange(ALL_GENRES)} />
      {genres.map((genre) => (
        <FilterPill
          key={genre}
          label={CATEGORY_LABELS[genre]}
          active={value === genre}
          onClick={() => onChange(genre)}
        />
      ))}
    </div>
  )
}

interface FilterPillProps {
  label: string
  active: boolean
  onClick: () => void
}

function FilterPill({ label, active, onClick }: FilterPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
        active
          ? 'bg-neutral-900 border-neutral-900 text-white'
          : 'bg-white border-neutral-200 text-neutral-600 hover:border-neutral-400'
      }`}
    >
      {label}
    </button>
  )
}
