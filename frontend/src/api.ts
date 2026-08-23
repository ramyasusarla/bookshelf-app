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

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Every user-scoped call takes the caller's Clerk session token as its first
// argument (fetched via Clerk's useAuth().getToken()) — search is the only
// endpoint that stays public, since it's just an unscoped Open Library proxy.
export async function fetchLibrary(token: string | null): Promise<LibraryEntry[]> {
  const response = await fetch(`${API_BASE_URL}/library`, { headers: authHeaders(token) })
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

export async function addToLibrary(
  token: string | null,
  payload: AddToLibraryPayload,
): Promise<LibraryEntry> {
  const response = await fetch(`${API_BASE_URL}/library`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Failed to add book (${response.status})`)
  }
  return response.json()
}

export async function startRanking(
  token: string | null,
  userBookId: number,
  tier: Tier,
): Promise<RankResult> {
  const response = await fetch(`${API_BASE_URL}/library/${userBookId}/rank`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify({ tier }),
  })
  if (!response.ok) {
    throw new Error(`Failed to start ranking (${response.status})`)
  }
  return response.json()
}

export async function submitRankChoice(
  token: string | null,
  sessionId: number,
  preferredUserBookId: number,
): Promise<RankResult> {
  const response = await fetch(`${API_BASE_URL}/library/rank-sessions/${sessionId}/choice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify({ preferred_user_book_id: preferredUserBookId }),
  })
  if (!response.ok) {
    throw new Error(`Failed to submit choice (${response.status})`)
  }
  return response.json()
}

export async function fetchRecommendations(
  token: string | null,
  category?: Category,
): Promise<RecommendationsResponse> {
  const url = new URL(`${API_BASE_URL}/recommendations`)
  if (category) url.searchParams.set('category', category)
  const response = await fetch(url, { headers: authHeaders(token) })
  if (!response.ok) {
    throw new Error(`Failed to fetch recommendations (${response.status})`)
  }
  return response.json()
}
