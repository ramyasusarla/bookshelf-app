import httpx

from app.schemas import BookSearchResult

SEARCH_URL = "https://openlibrary.org/search.json"
COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
WORK_URL = "https://openlibrary.org{work_key}.json"


async def search_books(query: str, limit: int = 20) -> list[BookSearchResult]:
    params = {
        "q": query,
        "limit": limit,
        "fields": "key,title,author_name,cover_i,first_publish_year",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()

    results = []
    for doc in data.get("docs", []):
        title = doc.get("title")
        if not title:
            continue
        cover_id = doc.get("cover_i")
        results.append(
            BookSearchResult(
                title=title,
                author=", ".join(doc.get("author_name", [])) or "Unknown",
                cover_url=COVER_URL.format(cover_id=cover_id) if cover_id else None,
                open_library_id=doc.get("key"),
                first_publish_year=doc.get("first_publish_year"),
            )
        )
    return results


async def fetch_description(work_key: str) -> str | None:
    """Fetch a work's description. work_key is the Open Library key, e.g. "/works/OL12345W"."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(WORK_URL.format(work_key=work_key))
        if response.status_code != 200:
            return None
        data = response.json()

    description = data.get("description")
    if isinstance(description, dict):
        return description.get("value")
    if isinstance(description, str):
        return description
    return None
