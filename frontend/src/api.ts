import type {
  AddToLibraryPayload,
  BookSearchResult,
  Category,
  LibraryEntry,
  RankResult,
  RecommendationsResponse,
  Tier,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export async function fetchLibrary(): Promise<LibraryEntry[]> {
  const response = await fetch(`${API_BASE_URL}/library`)
  if (!response.ok) {
    throw new Error(`Failed to fetch library (${response.status})`)
  }
  return response.json()
}

export async function searchBooks(query: string): Promise<BookSearchResult[]> {
  const response = await fetch(`${API_BASE_URL}/books/search?q=${encodeURIComponent(query)}`)
  if (!response.ok) {
    throw new Error(`Failed to search books (${response.status})`)
  }
  return response.json()
}

export async function addToLibrary(payload: AddToLibraryPayload): Promise<LibraryEntry> {
  const response = await fetch(`${API_BASE_URL}/library`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Failed to add book (${response.status})`)
  }
  return response.json()
}

export async function startRanking(userBookId: number, tier: Tier): Promise<RankResult> {
  const response = await fetch(`${API_BASE_URL}/library/${userBookId}/rank`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tier }),
  })
  if (!response.ok) {
    throw new Error(`Failed to start ranking (${response.status})`)
  }
  return response.json()
}

export async function submitRankChoice(
  sessionId: number,
  preferredUserBookId: number,
): Promise<RankResult> {
  const response = await fetch(`${API_BASE_URL}/library/rank-sessions/${sessionId}/choice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preferred_user_book_id: preferredUserBookId }),
  })
  if (!response.ok) {
    throw new Error(`Failed to submit choice (${response.status})`)
  }
  return response.json()
}

export async function fetchRecommendations(
  category?: Category,
): Promise<RecommendationsResponse> {
  const url = new URL(`${API_BASE_URL}/recommendations`)
  if (category) url.searchParams.set('category', category)
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to fetch recommendations (${response.status})`)
  }
  return response.json()
}
