import os
import logging
import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYBOOKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
CHROMA_DIR    = os.path.join(BASE_DIR, 'chroma_db')
COLLECTION    = 'playbooks'


def get_client():
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_DIR)


def parse_playbook_file(file_path: str) -> list[dict]:
    """
    Parse a .txt playbook file into structured chunks.
    Each --- separator creates a new chunk.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    source_name = os.path.splitext(os.path.basename(file_path))[0]
    sections    = content.split('---')
    chunks      = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract clause type
        clause_type = 'general'
        for line in section.split('\n'):
            if line.startswith('CLAUSE_TYPE:'):
                clause_type = line.replace('CLAUSE_TYPE:', '').strip().lower()
                break

        chunks.append({
            'text':        section,
            'source_name': source_name,
            'clause_type': clause_type,
        })

    return chunks


def load_all_playbooks(reset: bool = False) -> dict:
    """
    Load all .txt files from playbooks/data/ into ChromaDB.
    Set reset=True to clear and reload everything.
    """
    client     = get_client()
    model      = SentenceTransformer('all-MiniLM-L6-v2')
    collection = client.get_or_create_collection(
        name     = COLLECTION,
        metadata = {'hnsw:space': 'cosine'},
    )

    # Optionally reset
    if reset:
        try:
            client.delete_collection(COLLECTION)
            collection = client.get_or_create_collection(
                name     = COLLECTION,
                metadata = {'hnsw:space': 'cosine'},
            )
            logger.info('Playbook collection reset.')
        except Exception as e:
            logger.warning(f'Reset failed: {e}')

    if not os.path.exists(PLAYBOOKS_DIR):
        return {'success': False, 'error': f'Playbooks dir not found: {PLAYBOOKS_DIR}'}

    txt_files    = [f for f in os.listdir(PLAYBOOKS_DIR) if f.endswith('.txt')]
    total_chunks = 0
    loaded_files = []

    for filename in txt_files:
        file_path = os.path.join(PLAYBOOKS_DIR, filename)
        try:
            chunks = parse_playbook_file(file_path)
            if not chunks:
                continue

            texts      = [c['text']        for c in chunks]
            embeddings = model.encode(texts, show_progress_bar=False).tolist()
            ids        = [
                f'playbook_{os.path.splitext(filename)[0]}_{i}'
                for i in range(len(chunks))
            ]
            metadatas  = [
                {
                    'source_name': c['source_name'],
                    'clause_type': c['clause_type'],
                    'file':        filename,
                }
                for c in chunks
            ]

            collection.add(
                ids        = ids,
                embeddings = embeddings,
                documents  = texts,
                metadatas  = metadatas,
            )

            total_chunks += len(chunks)
            loaded_files.append(filename)
            logger.info(f'Loaded {filename}: {len(chunks)} chunks')

        except Exception as e:
            logger.error(f'Failed to load {filename}: {e}')

    return {
        'success':      True,
        'files_loaded': loaded_files,
        'total_chunks': total_chunks,
        'collection':   COLLECTION,
    }


def validate_retrieval() -> dict:
    """
    Test retrieval quality with sample queries.
    Returns results for inspection.
    """
    client     = get_client()
    model      = SentenceTransformer('all-MiniLM-L6-v2')
    collection = client.get_or_create_collection(
        name     = COLLECTION,
        metadata = {'hnsw:space': 'cosine'},
    )

    test_queries = [
        ('confidentiality period too short',    'confidentiality'),
        ('no liability cap in contract',         'limitation of liability'),
        ('termination without notice',           'termination'),
        ('ip ownership assigned to vendor',      'intellectual property'),
        ('automatic renewal clause',             'auto-renewal'),
        ('non-compete too broad',                'non-compete'),
        ('payment terms net 15',                 'payment terms'),
        ('data breach notification missing',     'data privacy'),
    ]

    results = []
    for query, expected_type in test_queries:
        query_embed = model.encode([query]).tolist()
        res         = collection.query(
            query_embeddings = query_embed,
            n_results        = 3,
        )

        top_clause_types = [
            m.get('clause_type', '') for m in res['metadatas'][0]
        ]
        hit = any(
            expected_type.lower() in t.lower() or t.lower() in expected_type.lower()
            for t in top_clause_types
        )

        results.append({
            'query':         query,
            'expected_type': expected_type,
            'got_types':     top_clause_types,
            'hit':           hit,
            'top_snippet':   res['documents'][0][0][:120] if res['documents'][0] else '',
        })

    hits  = sum(1 for r in results if r['hit'])
    total = len(results)

    return {
        'accuracy':     f'{hits}/{total}',
        'accuracy_pct': round(hits / total * 100),
        'results':      results,
    }