import os
import logging
from openai import OpenAI
from .embedder import query_contract, query_playbooks

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key  = os.getenv('GROQ_API_KEY', ''),
    base_url = 'https://api.groq.com/openai/v1',
)

SYSTEM_PROMPT = """You are a legal contract assistant. You help users understand their contracts.

You are given:
1. Relevant excerpts from the contract (CONTRACT CONTEXT)
2. Relevant legal standards from playbooks (PLAYBOOK CONTEXT)
3. The conversation history (last 10 turns)

Rules:
- Answer only based on the provided context. Do not hallucinate.
- Cite specific clauses when you reference contract text. Use the format: [Clause, chunk X]
- If the answer is not in the context, say: "I couldn't find that in the contract."
- Be concise and plain-English. Avoid unnecessary legal jargon.
- If a clause is risky, explain why clearly."""


def build_context(contract_id: int, query: str) -> tuple[str, list]:
    """
    Query contract + playbooks for the given query.
    Returns (context_string, citations_list).
    """
    contract_chunks = query_contract(contract_id, query, top_k=4)
    playbook_chunks = query_playbooks(query, top_k=2)

    citations = []
    ctx_parts = []

    if contract_chunks:
        ctx_parts.append('CONTRACT CONTEXT:')
        for i, chunk in enumerate(contract_chunks):
            ctx_parts.append(f'[Chunk {chunk["chunk_index"]}]\n{chunk["text"]}\n')
            citations.append({
                'type':        'contract',
                'chunk_index': chunk['chunk_index'],
                'excerpt':     chunk['text'][:120],
            })

    if playbook_chunks:
        ctx_parts.append('\nPLAYBOOK CONTEXT:')
        for chunk in playbook_chunks:
            ctx_parts.append(f'[{chunk["source"]} — {chunk["clause_type"]}]\n{chunk["text"]}\n')

    return '\n'.join(ctx_parts), citations


def run_chat_agent(contract_id: int, question: str, history: list) -> dict:
    """
    Main chat function.

    Args:
        contract_id: the contract being discussed
        question:    the user's latest message
        history:     list of last 10 dicts — [{'role': 'user'/'assistant', 'content': '...'}, ...]

    Returns:
        {
            'success':  bool,
            'answer':   str,
            'citations': list,
            'error':    str | None
        }
    """
    if not question or not question.strip():
        return {'success': False, 'answer': '', 'citations': [], 'error': 'Empty question.'}

    try:
        context, citations = build_context(contract_id, question)

        # Build messages list: system + history + new user message with context
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]

        # Inject history (last 10 turns already trimmed by caller)
        for turn in history:
            messages.append({'role': turn['role'], 'content': turn['content']})

        # Append current question with context injected
        user_message = f"""CONTEXT:
{context}

QUESTION:
{question}"""

        messages.append({'role': 'user', 'content': user_message})

        response = client.chat.completions.create(
            model      = 'llama-3.3-70b-versatile',
            max_tokens = 800,
            messages   = messages,
        )

        answer = response.choices[0].message.content.strip()

        return {
            'success':   True,
            'answer':    answer,
            'citations': citations,
            'error':     None,
        }

    except Exception as e:
        logger.error(f'Chat agent error for contract {contract_id}: {e}')
        return {
            'success':   False,
            'answer':    '',
            'citations': [],
            'error':     str(e),
        }