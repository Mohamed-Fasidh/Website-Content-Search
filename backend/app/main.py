from dotenv import load_dotenv
load_dotenv()

import hashlib
import os
import re
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_TOKEN_LIMIT = int(os.getenv("CHUNK_TOKEN_LIMIT", "500"))
TOP_K = int(os.getenv("TOP_K", "10"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "6"))   # crawl budget (start URL + up to N-1 links)

app = FastAPI(title="Website Content Search API (Pinecone)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

_embedder = None
_pc = None

def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedder

def pc():
    global _pc
    if _pc is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY not set")
        _pc = Pinecone(api_key=PINECONE_API_KEY)
    return _pc

def ensure_index(name: str, dim: int):
    client = pc()
    existing = {i["name"] for i in client.list_indexes()}
    if name not in existing:
        client.create_index(
            name=name, dimension=dim, metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=PINECONE_REGION),
        )

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def fetch_html(url: str) -> str:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def detect_page_path(url: str, html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        link = soup.find("link", attrs={"rel": ["canonical","Canonical","CANONICAL"]})
        if link and link.get("href"):
            abs_url = urljoin(url, link["href"])
            return urlparse(abs_url).path or "/"
    except Exception:
        pass
    return urlparse(url).path or "/"

def clean_html_and_get_dom_chunks(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]): tag.decompose()
    blocks = soup.find_all(["section","article","div","p","li"])
    out = []
    for tag in blocks:
        inner_html = "".join(str(c) for c in tag.contents)
        text = tag.get_text(" ", strip=True)
        if text and len(text) > 20:
            cleaned = normalize_space(inner_html)
            if cleaned: out.append(cleaned)
    if not out:
        body = soup.get_text(" ", strip=True)
        if body: out = [normalize_space(body)]
    return out

def tokenize_len(text: str) -> int:
    return len(re.findall(r"\w+|[^\w\s]", text))

def chunk_by_token_limit(snippets, limit: int):
    chunks, buf, buf_tokens = [], [], 0
    for snip in snippets:
        t = tokenize_len(snip)
        if t > limit:
            words = re.findall(r"\S+\s*", snip)
            tmp, tmp_tokens = [], 0
            for w in words:
                wt = tokenize_len(w)
                if tmp_tokens + wt > limit and tmp:
                    chunks.append("".join(tmp).strip()); tmp, tmp_tokens = [w], wt
                else:
                    tmp.append(w); tmp_tokens += wt
            if tmp: chunks.append("".join(tmp).strip())
            continue
        if buf_tokens + t > limit and buf:
            chunks.append(" ".join(buf).strip()); buf, buf_tokens = [snip], t
        else:
            buf.append(snip); buf_tokens += t
    if buf: chunks.append(" ".join(buf).strip())
    return chunks

def extract_title_from_html(html: str) -> str:
    try:
        s = BeautifulSoup(html, "html.parser")
        for tag in ["h1","h2","h3","strong","b","p","li"]:
            t = s.find(tag)
            if t and t.get_text(strip=True):
                return normalize_space(t.get_text(" ", strip=True))[:140]
    except Exception: pass
    return normalize_space(BeautifulSoup(html,"html.parser").get_text(" ", strip=True))[:140]

def upsert_chunks(client, index_name: str, site_id: str, page_url: str, page_path: str, chunks, embedder):
    index = client.Index(index_name)
    vecs = embedder.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
    to_upsert = []
    for i, (html, v) in enumerate(zip(chunks, vecs)):
        vid = hashlib.sha256(f"{page_url}#{i}".encode("utf-8")).hexdigest()[:40]
        to_upsert.append({
            "id": vid,
            "values": v.tolist(),
            "metadata": {
                "site_id": site_id,         # filter across the whole site
                "page_url": page_url,
                "path": page_path,
                "chunk_html": html,
                "title": extract_title_from_html(html),
            },
        })
    index.upsert(vectors=to_upsert)

def search_top_k(client, index_name: str, query: str, site_id: str, embedder, top_k: int):
    index = client.Index(index_name)
    qvec = embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0].tolist()
    res = index.query(
        vector=qvec, top_k=top_k * 3,
        filter={"site_id": {"$eq": site_id}},
        include_values=False, include_metadata=True,
    )
    out = []
    for m in res.get("matches", []):
        md = m.get("metadata") or {}
        score = float(m.get("score", 0.0))
        out.append({
            "raw_score": score,
            "score_percent": int(round((score + 1) / 2 * 100)),
            "chunk_html": md.get("chunk_html",""),
            "title": md.get("title"),
            "path": md.get("path","/"),
            "page_url": md.get("page_url"),
        })
    # dedupe by chunk
    seen, uniq = set(), []
    for r in out:
        k = r["chunk_html"][:200]
        if k not in seen and r["chunk_html"]:
            uniq.append(r); seen.add(k)
        if len(uniq) >= top_k: break
    return uniq

# ---- simple same-domain crawler ----
def same_domain_links(start_url: str, html: str, limit: int):
    soup = BeautifulSoup(html, "html.parser")
    origin = urlparse(start_url)
    seen = set([start_url])
    q = [start_url]
    for a in soup.find_all("a", href=True):
        if len(seen) >= limit: break
        href = urljoin(start_url, a["href"])
        u = urlparse(href)
        if u.scheme in ("http","https") and u.netloc == origin.netloc:
            if href not in seen:
                seen.add(href); q.append(href)
        if len(q) >= limit: break
    return q  # includes start_url first

class SearchRequest(BaseModel):
    url: str
    query: str

@app.post("/search")
def search(req: SearchRequest):
    embedder = get_embedder()
    dim = embedder.get_sentence_embedding_dimension()
    index_name = f"html-chunks-v3-{dim}"  # bump name to avoid stale metadata
    ensure_index(index_name, dim)

    # site-level filter id (scheme+host)
    u = urlparse(req.url)
    site_id = f"{u.scheme}://{u.netloc}"

    client = pc()

    # probe if site already indexed
    probe = search_top_k(client, index_name, "the", site_id, embedder, 1)
    if not probe:
        # index start page + a few same-domain links
        start_html = fetch_html(req.url)
        urls = same_domain_links(req.url, start_html, MAX_PAGES)
        for page_url in urls:
            try:
                html = start_html if page_url == req.url else fetch_html(page_url)
                path = detect_page_path(page_url, html)
                snippets = clean_html_and_get_dom_chunks(html)
                chunks = chunk_by_token_limit(snippets, CHUNK_TOKEN_LIMIT)
                if chunks:
                    upsert_chunks(client, index_name, site_id, page_url, path, chunks, embedder)
            except Exception:
                continue

    results = search_top_k(client, index_name, req.query, site_id, embedder, TOP_K)
    return {"results": results}
