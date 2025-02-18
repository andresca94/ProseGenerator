# main.py
# -*- coding: utf-8 -*-
"""
FastAPI backend for Beats-to-Prose generation.
This backend uses OpenAI GPT models and Pinecone to generate ~1500 words of narrative prose
from user-supplied story beats and optional metadata (characters, setting, genre, style).

Note: Data ingestion (embedding and upserting data into Pinecone) is skipped since the vectors are
already created and stored in Pinecone.
"""

import os
import re
import hashlib
import logging
import random
from datetime import datetime
from typing import List, Dict, Optional
from copy import copy

import openai
import pinecone
import numpy as np
from torch import nn
from sentence_transformers import CrossEncoder

from fastapi import FastAPI
from pydantic import BaseModel

# -------------------------------------------------------------------
# Debug/Logging Configuration
# -------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# API Keys & Configuration (replace with your keys or use env vars)
# -------------------------------------------------------------------
pinecone_key = os.getenv("PINECONE_API_KEY", "your-pinecone-key")
openai_key   = os.getenv("OPENAI_API_KEY", "your-openai-key")
openai.api_key = openai_key

# Choose model: "gpt-4" or "gpt-3.5-turbo" (adjust as needed)
GPT_MODEL = "gpt-4o-2024-08-06"
EMBED_MODEL = "text-embedding-3-large"
DIMENSION = 3072
INDEX_NAME = "semantic-search-booksum-improved"
NAMESPACE = "default"

# -------------------------------------------------------------------
# Pinecone Client Initialization
# -------------------------------------------------------------------
pinecone.init(api_key=pinecone_key, environment="us-east1-gcp")
index = pinecone.Index(INDEX_NAME)
logger.info("Pinecone client initialized and connected to index: %s", INDEX_NAME)

# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------
LOG_FILE_PATH = "semantic_search_logs.txt"

def log_to_file(message: str):
    """Append a message to a log file with a timestamp."""
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        timestamp = datetime.now().isoformat()
        f.write(f"\n[{timestamp}] {message}\n")

def my_hash(s: str) -> str:
    """Return the MD5 hash of a string for stable, unique IDs."""
    return hashlib.md5(s.encode()).hexdigest()

def chunk_text_by_paragraph(text: str, max_chunk_chars: int = 2000) -> List[str]:
    """
    Splits text by paragraphs, then combines paragraphs into chunks of up to max_chunk_chars
    so we don't cut in the middle of paragraphs or exceed the limit.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_length = 0
    for para in paragraphs:
        para_len = len(para)
        if current_length + para_len > max_chunk_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_length = para_len
        else:
            current_chunk.append(para)
            current_length += para_len
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks

def fix_snippet_start(snippet: str) -> str:
    """
    If the snippet starts in the middle of a sentence, remove everything
    up to (and including) the first encountered sentence-ending punctuation.
    """
    pattern = r'^[^.?!]*[.?!]\s*'
    cleaned = re.sub(pattern, '', snippet, count=1)
    return cleaned.strip()

def get_random_approx_1500_words(full_text: str, min_word_count: int = 1500, max_word_count: int = 1800) -> str:
    """
    Returns a random snippet of text whose length is between min_word_count and max_word_count words.
    Uses fix_snippet_start to avoid partial sentence fragments at the beginning.
    """
    words = full_text.split()
    total_words = len(words)
    if total_words < min_word_count:
        return ""
    snippet_length = random.randint(min_word_count, max_word_count)
    snippet_length = min(snippet_length, total_words)
    max_start_idx = total_words - snippet_length
    start_idx = random.randint(0, max_start_idx)
    end_idx = start_idx + snippet_length
    snippet_words = words[start_idx:end_idx]
    raw_snippet = " ".join(snippet_words).strip()
    cleaned_snippet = fix_snippet_start(raw_snippet)
    return cleaned_snippet

# -------------------------------------------------------------------
# Pinecone Query Functions (Vector Search)
# -------------------------------------------------------------------
def query_pinecone(query_text: str, top_k=3, namespace=NAMESPACE) -> List[Dict]:
    """
    Retrieve top_k results from Pinecone using embedding similarity.
    """
    logger.info("query_pinecone() => Query: %s", query_text[:60])
    response = openai.Embedding.create(model=EMBED_MODEL, input=[query_text])
    q_emb = response["data"][0]["embedding"]
    results = index.query(
        vector=q_emb,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True
    )
    return results.get("matches", [])

# -------------------------------------------------------------------
# Few-Shot Example Retrieval
# -------------------------------------------------------------------
def get_results_from_pinecone(query: str, top_k: int = 3, do_rerank: bool = True, verbose: bool = True) -> Dict[str, List[Dict]]:
    """
    Query Pinecone, optionally re-rank, then return final results.
    """
    log_to_file(f"Querying Pinecone with: {query}")
    pine_results = query_pinecone(query, top_k=top_k)
    if not pine_results:
        return {"final_results": []}

    if verbose:
        logger.info("Pinecone results (pre re-rank):")
        for r in pine_results:
            snippet = r["metadata"].get("text", "")[:50].replace("\n", " ")
            logger.info("ID=%s Score=%.4f => %s...", r["id"], r["score"], snippet)
            log_to_file(f"PineRaw => ID={r['id']} Score={r['score']:.4f}")

    if do_rerank:
        final = re_rank_results(query, pine_results)
    else:
        final = pine_results

    if verbose:
        logger.info("Final results after re-rank:")
        for r in final:
            snippet = r["metadata"].get("text", "")[:50].replace("\n", " ")
            logger.info("-> ID=%s Score=%.4f => %s...", r["id"], r["score"], snippet)
        log_to_file("Top Pinecone Results:\n" + "\n".join(
            [f"ID={r['id']} Score={r['score']:.4f}" for r in final]
        ))
    return {"final_results": final}

# Cross-Encoder for re-ranking
cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2', num_labels=1)

def re_rank_results(query: str, pine_results: List[Dict]) -> List[Dict]:
    """
    Use a cross-encoder to re-rank pine_results by relevance.
    """
    if len(pine_results) < 2:
        return pine_results
    combos = [[query, r["metadata"].get("text", "")] for r in pine_results]
    scores = cross_encoder.predict(combos, activation_fct=nn.Sigmoid())
    logger.info("Cross-Encoder Re-rank scores:")
    for i, r in enumerate(pine_results):
        snippet = r["metadata"].get("text", "")[:50].replace("\n", " ")
        logger.info("ID=%s OriginalScore=%.4f, CE_Score=%.4f => %s...", r['id'], r['score'], scores[i], snippet)
        log_to_file(f"Re-rank => ID={r['id']} PineScore={r['score']:.4f}, CE_Score={scores[i]:.4f}")
    sorted_idxs = list(reversed(np.argsort(scores)))
    re_ranked = []
    for idx in sorted_idxs:
        item = pine_results[idx]
        item["score"] = float(scores[idx])
        re_ranked.append(item)
    return re_ranked

def retrieve_few_shot_examples(query: str, top_k: int = 2, re_rank: bool = False, verbose: bool = True) -> List[Dict]:
    """
    Fetch a few short example passages from Pinecone to serve as few-shot examples.
    """
    results_dict = get_results_from_pinecone(query=query, top_k=top_k, do_rerank=re_rank, verbose=verbose)
    final_matches = results_dict["final_results"]
    few_shot_msgs = []
    for res in final_matches:
        chapter_text = res["metadata"].get("chapter", "")
        if not chapter_text.strip():
            continue
        content = (
            "This is a sample excerpt from a chapter:\n\n"
            f"{chapter_text}\n\n"
            "End of sample excerpt."
        )
        few_shot_msgs.append({"role": "assistant", "content": content})
    return few_shot_msgs

# -------------------------------------------------------------------
# GPT Interaction Functions
# -------------------------------------------------------------------
def chat_with_gpt(prompt: str, model: str = GPT_MODEL) -> str:
    """
    Sends a prompt to GPT and returns the model's response.
    """
    logger.info("chat_with_gpt() => Sending prompt to GPT.")
    logger.debug("Prompt: %s", prompt[:1000] + "..." if len(prompt) > 1000 else prompt)
    completion = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    response = completion.choices[0].message.content
    logger.info("Received response from GPT.")
    return response

def generate_prose_iteratively(prompt: str, desired_min=1400, desired_max=1600, max_iterations=3) -> str:
    """
    Iteratively call GPT until the output word count is within the desired range.
    """
    iteration = 0
    final_response = ""
    current_prompt = prompt
    while iteration < max_iterations:
        iteration += 1
        logger.info("Iteration %d: Sending prompt to GPT.", iteration)
        response = chat_with_gpt(current_prompt, model=GPT_MODEL)
        word_count = len(response.split())
        logger.info("Word count is %d.", word_count)
        if desired_min <= word_count <= desired_max:
            final_response = response
            break
        else:
            if word_count < desired_min:
                additional_instructions = (
                    f"Your previous output had only {word_count} words, but we need at least {desired_min}. "
                    "Please extend the story with additional details and scenes while maintaining coherence."
                )
            else:
                additional_instructions = (
                    f"Your previous output had {word_count} words, but we need at most {desired_max}. "
                    "Please condense the story while keeping the main narrative intact."
                )
            current_prompt = (
                f"The current draft of your story is below:\n\n{response}\n\n{additional_instructions}"
            )
    return final_response if final_response else response

# -------------------------------------------------------------------
# Prose Generation Functions
# -------------------------------------------------------------------
def generate_prose_from_beats(beats: List[str]) -> str:
    """
    Given a list of story beats, generate approximately 1500 words of prose.
    """
    log_to_file(f"Received Beats:\n{beats}")
    instructions = (
        "You are a skilled novel writer. You will receive a series of story beats. "
        "Your task is to write ~1500 words of cohesive, flowing prose in a novelistic style."
    )
    beats_text = "\n".join(f"{i+1}. {beat}" for i, beat in enumerate(beats))
    final_prompt = f"{instructions}\n\nHere are the story beats:\n{beats_text}\n\nNow please generate the prose:\n"
    prose = generate_prose_iteratively(final_prompt, desired_min=1400, desired_max=1600, max_iterations=3)
    word_count = len(prose.split())
    logger.info("The GPT response word count: %d words.", word_count)
    log_to_file(f"GPT Output:\n{prose}")
    return prose

def create_gpt_overview(beats: List[str], setting: str, genre: str, style: str) -> str:
    """
    Call GPT to produce a short 'overview' (~2-4 paragraphs) that ties beats with setting, genre, and style.
    """
    prompt = (
        "You are a summary generator. Please read the following details:\n\n"
        f"Beats:\n{chr(10).join(beats)}\n\n"
        f"Setting: {setting}\n"
        f"Genre: {genre}\n"
        f"Style: {style}\n\n"
        "Create a concise overview (2-4 paragraphs) that ties all these details together."
    )
    log_to_file(f"[GPT Overview] Prompt:\n{prompt}")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0125",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    overview_text = response.choices[0].message.content.strip()
    log_to_file(f"[GPT Overview] Response:\n{overview_text}")
    return overview_text

def generate_prose_with_metadata(
    beats: List[str],
    characters: Optional[List[Dict]] = None,
    setting: str = "",
    genre: str = "",
    style: str = "",
    approx_word_count: int = 1500,
    top_k: int = 5,
    re_rank: bool = True,
    few_shot_query: str = "example sci-fi chapter excerpt",
    few_shot_top_k: int = 2
) -> str:
    """
    Generate prose based on beats and additional metadata:
    - Create an overview from the beats.
    - Retrieve reference passages from Pinecone.
    - Retrieve few-shot examples for style inspiration.
    - Construct a final prompt and iteratively generate prose.
    """
    log_to_file(f"[Generate] Beats:\n{beats}")
    log_to_file(f"[Generate] Characters:\n{characters}")
    log_to_file(f"[Generate] Setting='{setting}', Genre='{genre}', Style='{style}'")
    # 1) Generate overview text from beats
    overview_text = create_gpt_overview(beats, setting, genre, style)
    # 2) Retrieve references from Pinecone using the overview text
    retrieval = get_results_from_pinecone(query=overview_text, top_k=top_k, do_rerank=re_rank, verbose=True)
    final_results = retrieval["final_results"]
    references_text = []
    for res in final_results:
        ref_text = res["metadata"].get("chapter", "")
        if not ref_text.strip():
            ref_text = res["metadata"].get("text", "")
        references_text.append(ref_text)
    combined_references = "\n\n".join(references_text)
    log_to_file("[DEBUG] Combined References:\n" + combined_references)
    # 3) Retrieve few-shot examples (for inspiration only)
    few_shot_examples = retrieve_few_shot_examples(
        query=few_shot_query,
        top_k=few_shot_top_k,
        re_rank=re_rank,
        verbose=False
    )
    # 4) Construct final user prompt
    char_block = ""
    if characters:
        for c in characters:
            name = c.get("name", "Unknown")
            desc = c.get("description", "N/A")
            char_block += f"- {name}: {desc}\n"
    beats_str = "\n".join(f"{i+1}. {b}" for i, b in enumerate(beats))
    final_user_prompt = f"""
Beats:
{beats_str}

Characters:
{char_block}

Setting: {setting}
Genre: {genre}
Style: {style}

Retrieved references (top {top_k}):
{combined_references}

Please write approximately {approx_word_count} words of cohesive, flowing prose
that follows these beats in order and incorporates the setting, genre, and style.
Use the references as inspiration for tone, but do not copy them verbatim.
"""
    # 5) Iteratively generate prose
    prose = generate_prose_iteratively(
        prompt=final_user_prompt,
        desired_min=int(approx_word_count*0.9),
        desired_max=int(approx_word_count*1.1),
        max_iterations=3
    )
    log_to_file("[DEBUG] GPT Response:\n" + prose)
    word_count = len(prose.split())
    logger.info("The GPT response word count: %d words.", word_count)
    if (approx_word_count * 0.9) <= word_count <= (approx_word_count * 1.1):
        logger.info("The response is within +/-10%% of the target.")
    else:
        logger.warning("The response length deviates significantly from target.")
    return prose

# -------------------------------------------------------------------
# FastAPI Setup & Endpoint
# -------------------------------------------------------------------
app = FastAPI(title="Beats-to-Prose Generator")

class ProseRequest(BaseModel):
    beats: List[str]
    characters: Optional[List[Dict]] = None
    setting: str = ""
    genre: str = ""
    style: str = ""

@app.post("/generate-prose")
async def beat_to_prose_endpoint(req: ProseRequest):
    """
    Endpoint for generating ~1500 words of prose.
    Receives a JSON body with beats, characters, setting, genre, and style.
    """
    # For basic beats-only generation, you could call generate_prose_from_beats(req.beats)
    # For full metadata-based generation, we use the following:
    output_text = generate_prose_with_metadata(
        beats=req.beats,
        characters=req.characters,
        setting=req.setting,
        genre=req.genre,
        style=req.style,
        approx_word_count=1500
    )
    return {"prose_output": output_text}

# -------------------------------------------------------------------
# Main entry point for local development
# -------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
