# Website Content Search — React + FastAPI + Pinecone

A single-page app where users input a **Website URL** and a **Search Query**.  
The backend fetches the HTML, parses & chunks it (≤500 tokens), embeds with Sentence Transformers, indexes in **Pinecone (serverless)**, and returns the **top 10** most relevant DOM chunks.

## Tech
- **Frontend:** React (Vite)
- **Backend:** FastAPI (Python)
- **Vector DB:** Pinecone (serverless)
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2`
- **Parsing:** BeautifulSoup
- **Env:** `.env` with `python-dotenv`

## Setup

### 1) Backend
```bash
cd backend
python -m venv .venv 
.venv\Scripts\activate
pip install -r requirements.txt
  
# edit .env to put your real Pinecone key + region
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2) Frontend
```bash
cd frontend
npm i
npm run dev
```
Open http://localhost:5173

## How it works
1. Fetch & parse HTML (scripts/styles removed).
2. Chunk DOM blocks into ≤500 tokens.
3. Embed with `all-MiniLM-L6-v2`.
4. Upsert to Pinecone (cosine metric).
5. Query Pinecone with the embedded search string; filter by `url_hash`.
6. Return top-10 unique chunks with **title**, **path**, and **match %**.

## Env Vars (`backend/.env`)
```
PINECONE_API_KEY=YOUR_REAL_API_KEY
PINECONE_REGION=us-east-1

```

