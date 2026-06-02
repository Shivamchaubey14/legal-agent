import dotenv
from langchain_groq import ChatGroq
dotenv.load_dotenv()  # Load environment variables from .env file
import os
import json
import logging
from typing import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from contracts.utils.embedder import query_contract, query_playbooks

logger = logging.getLogger(__name__)

# ── Anthropic client ─────────────────────────────────────────
def get_llm():
    return ChatGroq(
        model='llama-3.3-70b-versatile',
        api_key=os.environ.get('GROQ_API_KEY'),
        max_tokens=1024,
    )


# ── Agent state ──────────────────────────────────────────────
class AgentState(TypedDict):
    contract_id:  int
    contract_text: str
    flags:        Annotated[list, operator.add]
    chunks_done:  int
    total_chunks: int


# ── Clause types to detect ───────────────────────────────────
CLAUSE_QUERIES = [
    ('termination',           'termination notice period cure breach'),
    ('liability',             'limitation of liability cap consequential damages'),
    ('confidentiality',       'confidentiality nda non-disclosure obligation'),
    ('ip',                    'intellectual property ownership rights assignment'),
    ('payment',               'payment terms invoice due date late fees'),
    ('non-compete',           'non-compete non-solicitation restriction'),
    ('governing_law',         'governing law jurisdiction dispute resolution'),
    ('indemnification',       'indemnification hold harmless defend claims'),
    ('data_privacy',          'data privacy breach notification personal data'),
    ('auto_renewal',          'automatic renewal cancellation notice'),
]


# ── Node 1: Search contract for each clause type ─────────────
def search_node(state: AgentState) -> AgentState:
    contract_id = state['contract_id']
    all_flags   = []

    llm = get_llm()

    for clause_type, query in CLAUSE_QUERIES:
        try:
            # Search contract chunks
            contract_chunks = query_contract(contract_id, query, top_k=3)
            if not contract_chunks:
                logger.info(f'No chunks found for {clause_type}')
                continue

            contract_text = '\n\n'.join(
                c.get('text', c) if isinstance(c, dict) else c
                for c in contract_chunks
            )

            # Search playbook for standard clause
            playbook_chunks = query_playbooks(query, top_k=2)
            playbook_text = '\n\n'.join(
                c.get('text', c) if isinstance(c, dict) else c
                for c in playbook_chunks
            ) if playbook_chunks else 'No standard playbook found for this clause type.'

            # Ask Claude to analyze
            system_prompt = """You are a legal contract review expert. 
Analyze the contract clause against the standard playbook clause.
Respond ONLY with a valid JSON object. No explanation, no markdown, no code blocks.
The JSON must have exactly these keys:
{
  "has_issue": true or false,
  "clause_type": "string",
  "risk_level": "low" or "medium" or "high" or "critical",
  "clause_text": "the exact problematic text from the contract (max 500 chars)",
  "reason": "why this is risky (1-2 sentences)",
  "suggestion": "specific recommended fix (1-2 sentences)"
}
If no issue found, return: {"has_issue": false}"""

            user_prompt = f"""CLAUSE TYPE: {clause_type}

CONTRACT TEXT:
{contract_text[:2000]}

STANDARD PLAYBOOK:
{playbook_text[:1500]}

Analyze the contract text against the playbook standard. 
Is there a risk or deviation? Respond with JSON only."""

            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])

            raw = response.content.strip()

            # Strip markdown if Claude wrapped it anyway
            # Find the first { and last } to extract clean JSON
            start = raw.find('{')
            end   = raw.rfind('}') + 1
            if start != -1 and end > start:
                raw = raw[start:end]

            result = json.loads(raw)

            if result.get('has_issue'):
                all_flags.append({
                    'clause_type': result.get('clause_type', clause_type),
                    'risk_level':  result.get('risk_level', 'medium'),
                    'clause_text': result.get('clause_text', '')[:1000],
                    'reason':      result.get('reason', ''),
                    'suggestion':  result.get('suggestion', ''),
                })
                logger.info(f'Flag found: {clause_type} → {result.get("risk_level")}')
            else:
                logger.info(f'No issue: {clause_type}')

        except json.JSONDecodeError as e:
            logger.error(f'JSON parse error for {clause_type}: {e} | raw: {raw[:200]}')
        except Exception as e:
            logger.error(f'Agent error for {clause_type}: {e}')
            continue

    return {'flags': all_flags, 'chunks_done': len(CLAUSE_QUERIES)}


# ── Node 2: Save flags to DB and compute risk score ──────────
def save_node(state: AgentState) -> AgentState:
    from contracts.models import Contract, ClauseFlag

    contract_id = state['contract_id']
    flags       = state['flags']

    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        logger.error(f'Contract {contract_id} not found in save_node')
        return state

    # Delete old flags for this contract
    ClauseFlag.objects.filter(contract=contract).delete()

    # Save new flags
    for flag in flags:
        ClauseFlag.objects.create(
            contract    = contract,
            clause_type = flag['clause_type'],
            risk_level  = flag['risk_level'],
            clause_text = flag['clause_text'],
            reason      = flag['reason'],
            suggestion  = flag['suggestion'],
        )

    # ── Compute overall risk score ────────────────────────────
    # Weights: critical=4, high=3, medium=2, low=1
    weights    = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
    score      = sum(weights.get(f['risk_level'], 1) for f in flags)
    max_score  = len(CLAUSE_QUERIES) * 4   # if every clause were critical

    if score == 0:
        risk_score = 'low'
    elif score <= max_score * 0.25:
        risk_score = 'low'
    elif score <= max_score * 0.50:
        risk_score = 'medium'
    elif score <= max_score * 0.75:
        risk_score = 'high'
    else:
        risk_score = 'critical'

    contract.risk_score = risk_score
    contract.status     = 'done'
    contract.save(update_fields=['risk_score', 'status'])

    logger.info(
        f'Contract {contract_id} analysis done — '
        f'{len(flags)} flags, risk_score={risk_score}'
    )
    return state


# ── Build the LangGraph ──────────────────────────────────────
def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node('search', search_node)
    graph.add_node('save',   save_node)

    graph.set_entry_point('search')
    graph.add_edge('search', 'save')
    graph.add_edge('save',   END)

    return graph.compile()


# ── Public entry point ───────────────────────────────────────
def analyze_contract(contract_id: int) -> dict:
    """
    Run the full clause detection agent on a contract.
    Called from Celery task in Day 8.
    """
    agent = build_agent()

    initial_state = {
        'contract_id':   contract_id,
        'contract_text': '',
        'flags':         [],
        'chunks_done':   0,
        'total_chunks':  len(CLAUSE_QUERIES),
    }

    try:
        final_state = agent.invoke(initial_state)
        return {
            'success':    True,
            'flags_found': len(final_state['flags']),
            'flags':      final_state['flags'],
        }
    except Exception as e:
        logger.error(f'Agent failed for contract {contract_id}: {e}')
        return {'success': False, 'error': str(e)}