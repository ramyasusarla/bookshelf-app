from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers.books import router as books_router
from app.routers.recommendations import router as recommendations_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bookshelf API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router)
app.include_router(recommendations_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
