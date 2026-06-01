import os
import re
import logging
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHROMA_DIR = os.path.join(BASE_DIR, 'chroma_db')

# ── Constants ────────────────────────────────────────────────
CHUNK_SIZE    = 500   # tokens approx (we use words as proxy)
CHUNK_OVERLAP = 50
MODEL_NAME    = 'all-MiniLM-L6-v2'
COLLECTION_CONTRACTS = 'contracts'
COLLECTION_PLAYBOOKS = 'playbooks'

# ── Singleton model (loaded once) ───────────────────────────
_model = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f'Loading embedding model: {MODEL_NAME}')
        _model = SentenceTransformer(MODEL_NAME)
        logger.info('Embedding model loaded.')
    return _model


# ── ChromaDB client (persistent) ────────────────────────────
def get_chroma_client() -> chromadb.PersistentClient:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_DIR)


def get_collection(name: str):
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={'hnsw:space': 'cosine'},
    )


# ── Chunking ─────────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping word-based chunks.
    chunk_size=500 words ≈ 500 tokens for MiniLM.
    """
    if not text or not text.strip():
        return []

    # Normalize whitespace
    text  = re.sub(r'\n{3,}', '\n\n', text)
    words = text.split()

    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start  = 0

    while start < len(words):
        end   = min(start + chunk_size, len(words))
        chunk = ' '.join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - overlap

    return chunks


# ── Embed & store a contract ─────────────────────────────────
def embed_contract(contract_id: int, text: str) -> dict:
    """
    Chunks and embeds a contract's raw text into ChromaDB.
    Returns summary dict.
    """
    if not text or not text.strip():
        return {'success': False, 'error': 'No text to embed', 'chunks': 0}

    try:
        collection = get_collection(COLLECTION_CONTRACTS)
        model      = get_model()
        chunks     = chunk_text(text)

        if not chunks:
            return {'success': False, 'error': 'Chunking produced no output', 'chunks': 0}

        # Delete any existing embeddings for this contract
        try:
            existing = collection.get(where={'contract_id': str(contract_id)})
            if existing['ids']:
                collection.delete(ids=existing['ids'])
                logger.info(f'Deleted {len(existing["ids"])} old chunks for contract {contract_id}')
        except Exception:
            pass

        # Embed all chunks in one batch
        embeddings = model.encode(chunks, show_progress_bar=False).tolist()

        ids        = [f'contract_{contract_id}_chunk_{i}' for i in range(len(chunks))]
        metadatas  = [
            {
                'contract_id': str(contract_id),
                'chunk_index': str(i),
                'chunk_total': str(len(chunks)),
            }
            for i in range(len(chunks))
        ]

        collection.add(
            ids        = ids,
            embeddings = embeddings,
            documents  = chunks,
            metadatas  = metadatas,
        )

        logger.info(f'Embedded contract {contract_id}: {len(chunks)} chunks stored.')
        return {
            'success':    True,
            'chunks':     len(chunks),
            'collection': COLLECTION_CONTRACTS,
            'error':      None,
        }

    except Exception as e:
        logger.error(f'Embedding failed for contract {contract_id}: {e}')
        return {'success': False, 'error': str(e), 'chunks': 0}


# ── Delete a contract's embeddings ──────────────────────────
def delete_contract_embeddings(contract_id: int) -> bool:
    """Delete all chunks for a contract from ChromaDB."""
    try:
        collection = get_collection(COLLECTION_CONTRACTS)
        existing   = collection.get(where={'contract_id': str(contract_id)})
        if existing['ids']:
            collection.delete(ids=existing['ids'])
            logger.info(f'Deleted embeddings for contract {contract_id}')
        return True
    except Exception as e:
        logger.error(f'Delete embeddings failed for contract {contract_id}: {e}')
        return False


# ── Query a contract ─────────────────────────────────────────
def query_contract(contract_id: int, query: str, top_k: int = 5) -> list[dict]:
    """
    Semantic search within a single contract.
    Returns top_k most relevant chunks.
    """
    try:
        collection  = get_collection(COLLECTION_CONTRACTS)
        model       = get_model()
        query_embed = model.encode([query]).tolist()

        results = collection.query(
            query_embeddings = query_embed,
            n_results        = top_k,
            where            = {'contract_id': str(contract_id)},
        )

        chunks = []
        for i, doc in enumerate(results['documents'][0]):
            chunks.append({
                'text':        doc,
                'chunk_index': results['metadatas'][0][i].get('chunk_index'),
                'distance':    results['distances'][0][i],
            })

        return chunks

    except Exception as e:
        logger.error(f'Query failed for contract {contract_id}: {e}')
        return []


# ── Query playbooks ──────────────────────────────────────────
def query_playbooks(query: str, top_k: int = 5) -> list[dict]:
    """
    Semantic search across all legal playbooks.
    Returns top_k most relevant playbook chunks.
    """
    try:
        collection  = get_collection(COLLECTION_PLAYBOOKS)
        model       = get_model()
        query_embed = model.encode([query]).tolist()

        results = collection.query(
            query_embeddings = query_embed,
            n_results        = top_k,
        )

        chunks = []
        for i, doc in enumerate(results['documents'][0]):
            chunks.append({
                'text':        doc,
                'source':      results['metadatas'][0][i].get('source_name', 'playbook'),
                'clause_type': results['metadatas'][0][i].get('clause_type', ''),
                'distance':    results['distances'][0][i],
            })

        return chunks

    except Exception as e:
        logger.error(f'Playbook query failed: {e}')
        return []


# ── Query both contract + playbooks ─────────────────────────
def query_combined(contract_id: int, query: str, top_k: int = 4) -> dict:
    """
    Query both contract and playbooks simultaneously.
    Used by the AI chat agent.
    """
    contract_chunks = query_contract(contract_id, query, top_k=top_k)
    playbook_chunks = query_playbooks(query, top_k=top_k)

    return {
        'contract_chunks': contract_chunks,
        'playbook_chunks': playbook_chunks,
        'query':           query,
    }


# ── Collection stats ─────────────────────────────────────────
def get_collection_stats() -> dict:
    """Return stats about both collections."""
    try:
        contracts_col = get_collection(COLLECTION_CONTRACTS)
        playbooks_col = get_collection(COLLECTION_PLAYBOOKS)
        return {
            'contracts_chunks': contracts_col.count(),
            'playbooks_chunks': playbooks_col.count(),
            'chroma_dir':       CHROMA_DIR,
        }
    except Exception as e:
        return {'error': str(e)}