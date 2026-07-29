export type Category =
  | 'fantasy'
  | 'sci_fi'
  | 'mystery'
  | 'romance'
  | 'historical_fiction'
  | 'realistic_fiction'
  | 'biography'
  | 'memoir'
  | 'self_help'
  | 'history'

export const CATEGORY_LABELS: Record<Category, string> = {
  fantasy: 'Fantasy',
  sci_fi: 'Sci-Fi',
  mystery: 'Mystery',
  romance: 'Romance',
  historical_fiction: 'Historical Fiction',
  realistic_fiction: 'Realistic Fiction',
  biography: 'Biography',
  memoir: 'Memoir',
  self_help: 'Self-Help',
  history: 'History',
}

export type ReadStatus = 'bookmarked' | 'reading' | 'read'

export type Tier = 'did_not_like' | 'it_was_alright' | 'liked_it'

export interface Book {
  id: number
  title: string
  author: string
  cover_url: string | null
  description: string | null
  category: Category | null
  open_library_id: string | null
}

export interface LibraryEntry {
  id: number
  status: ReadStatus
  rating: number | null
  tier: Tier | null
  rank_position: number | null
  date_completed: string | null
  created_at: string
  book: Book
}

export interface BookSearchResult {
  title: string
  author: string
  cover_url: string | null
  description: string | null
  open_library_id: string | null
  first_publish_year: number | null
}

// Mirrors the backend's AddToLibraryRequest, minus status/date_completed:
// this dialog never sets read/unread state — the ranking flow owns that.
export interface AddToLibraryPayload {
  title: string
  author: string
  cover_url: string | null
  description: string | null
  open_library_id: string | null
  category: Category
}

export interface ComparisonCandidate {
  user_book_id: number
  title: string
  author: string
  cover_url: string | null
}

export interface RankComparisonResult {
  outcome: 'comparing'
  session_id: number
  new_book: ComparisonCandidate
  candidate_book: ComparisonCandidate
}

export interface RankPlacedResult {
  outcome: 'placed'
  user_book: LibraryEntry
}

export type RankResult = RankComparisonResult | RankPlacedResult

export interface Recommendation {
  title: string
  author: string
  cover_url: string | null
  description: string | null
  open_library_id: string
  similarity: number
}

export interface RecommendationsResponse {
  recommendations: Recommendation[]
  message: string | null
}
