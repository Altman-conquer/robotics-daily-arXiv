#!/usr/bin/env python3
import argparse
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from tqdm import tqdm


DEFAULT_RESULT = {
    "relevant": False,
    "confidence": 0.0,
    "reason": "Classifier failed closed; paper excluded for strict topic filtering.",
    "topics": [],
}


SYSTEM_PROMPT = """
You are an expert curator for an embodied AI and robotics paper feed.

User research scope:
{scope}

Keep a paper if it is substantially relevant to embodied intelligence, including:
- vision-language-action models, VLAs, world models, world-action models, robot foundation models;
- robot learning, manipulation, dexterous manipulation, locomotion, navigation, grasping, teleoperation;
- embodied agents, physical AI, sim-to-real, robot policy learning, visuomotor control, affordance learning;
- autonomous driving or mobile agents when the paper is about embodied perception, planning, control, or action.

Reject a paper if it is mainly about generic computer vision, NLP, LLM reasoning, optimization, theory,
image/video generation, retrieval, datasets, security, medicine, or generic reinforcement learning without a
clear embodied agent, robot, physical action, control, or world-modeling connection.

Return only a valid JSON object with this schema:
{{"relevant": true/false, "confidence": 0.0-1.0, "reason": "one short sentence", "topics": ["short topic label"]}}
"""


HUMAN_PROMPT = """
Title: {title}
Categories: {categories}
Authors: {authors}
Comment: {comment}
Abstract:
{summary}
"""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def load_jsonl(path: str) -> List[dict]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def write_jsonl(path: str, items: Iterable[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def message_content_to_text(response) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def parse_classifier_response(response) -> Dict:
    text = message_content_to_text(response).strip()
    candidates = [text]
    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        candidates.append(fenced_match.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed, _ = decoder.raw_decode(candidate.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "relevant" in parsed:
            try:
                confidence = float(parsed.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            topics = parsed.get("topics", [])
            if not isinstance(topics, list):
                topics = []
            return {
                "relevant": bool(parsed.get("relevant")),
                "confidence": confidence,
                "reason": str(parsed.get("reason", ""))[:500],
                "topics": [str(topic)[:80] for topic in topics[:8]],
            }
    return dict(DEFAULT_RESULT)


def invoke_with_retries(chain, payload: Dict[str, str], item_id: str):
    max_retries = max(0, env_int("TOPIC_FILTER_REQUEST_RETRIES", env_int("AI_REQUEST_RETRIES", 3)))
    base_delay = max(0.1, env_float("TOPIC_FILTER_RETRY_BASE_SECONDS", env_float("AI_RETRY_BASE_SECONDS", 2.0)))
    max_delay = max(base_delay, env_float("TOPIC_FILTER_RETRY_MAX_SECONDS", env_float("AI_RETRY_MAX_SECONDS", 60.0)))
    stagger = max(0.0, env_float("TOPIC_FILTER_REQUEST_STAGGER_SECONDS", env_float("AI_REQUEST_STAGGER_SECONDS", 0.0)))

    if stagger:
        time.sleep(random.uniform(0, stagger))

    for attempt in range(max_retries + 1):
        try:
            return chain.invoke(payload)
        except Exception as e:
            if attempt >= max_retries:
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            delay += random.uniform(0, min(base_delay, delay))
            print(
                f"Topic classifier failed for {item_id}, retry {attempt + 1}/{max_retries} in {delay:.1f}s: {e}",
                file=sys.stderr,
            )
            time.sleep(delay)


def classify_item(chain, item: dict, scope: str) -> dict:
    item_id = item.get("id", "unknown")
    try:
        response = invoke_with_retries(
            chain,
            {
                "scope": scope,
                "title": item.get("title", ""),
                "categories": ", ".join(item.get("categories") or []),
                "authors": ", ".join(item.get("authors") or []),
                "comment": item.get("comment", ""),
                "summary": item.get("summary", ""),
            },
            item_id,
        )
        result = parse_classifier_response(response)
        if result == DEFAULT_RESULT:
            print(f"Using fail-closed topic result for {item_id}: invalid classifier JSON", file=sys.stderr)
        if (
            not result.get("relevant", True)
            and result.get("confidence", 0.0) < env_float("TOPIC_FILTER_MIN_CONFIDENCE", 0.65)
            and env_bool("TOPIC_FILTER_KEEP_UNCERTAIN", False)
        ):
            result = dict(result)
            result["relevant"] = True
            result["reason"] = f"uncertain_keep: {result.get('reason', '')}"
        return result
    except Exception as e:
        print(f"Topic classifier unexpected error for {item_id}; using fail-closed result: {e}", file=sys.stderr)
        return dict(DEFAULT_RESULT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to the daily JSONL file")
    args = parser.parse_args()

    if not env_bool("TOPIC_FILTER_ENABLED", False):
        print("Topic filter disabled; keeping all papers", file=sys.stderr)
        return 0

    model_name = os.environ.get("TOPIC_FILTER_MODEL_NAME") or os.environ.get("MODEL_NAME", "gpt-4o-mini")
    max_workers = max(1, env_int("TOPIC_FILTER_MAX_WORKERS", env_int("AI_MAX_WORKERS", 1)))
    scope = os.environ.get(
        "TOPIC_FILTER_SCOPE",
        "Embodied AI, VLA, world model, world action model, robot learning, robot policy/control/planning, "
        "manipulation, locomotion, navigation, autonomous driving agents, sim-to-real, visuomotor learning, "
        "affordance, physical AI, dexterous or bimanual systems, robot foundation models, and benchmarks, "
        "datasets, or evaluation directly targeting embodied agents.",
    )

    items = load_jsonl(args.data)
    print(
        f"LLM topic filter: model={model_name}, workers={max_workers}, papers={len(items)}",
        file=sys.stderr,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT),
    ])
    chain = prompt | ChatOpenAI(model=model_name)

    results = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(classify_item, chain, item, scope): idx
            for idx, item in enumerate(items)
        }
        for future in tqdm(as_completed(future_to_idx), total=len(items), desc="Filtering topics"):
            idx = future_to_idx[future]
            results[idx] = future.result()

    kept = []
    excluded = []
    for item, result in zip(items, results):
        annotated = dict(item)
        annotated["topic_filter"] = result
        if result.get("relevant", True):
            kept.append(annotated)
        else:
            excluded.append(annotated)

    if not kept:
        print(
            f"LLM topic filter removed all {len(items)} papers; leaving input unchanged to avoid empty output",
            file=sys.stderr,
        )
        return 2

    excluded_path = os.environ.get("TOPIC_FILTER_EXCLUDED_PATH", "").strip()
    if not excluded_path:
        excluded_path = os.path.join(
            "logs",
            os.path.basename(args.data).replace(".jsonl", "_topic_excluded.jsonl"),
        )
    try:
        os.makedirs(os.path.dirname(excluded_path) or ".", exist_ok=True)
    except OSError:
        excluded_path = os.path.join(
            "/tmp",
            os.path.basename(args.data).replace(".jsonl", "_topic_excluded.jsonl"),
        )
        os.makedirs(os.path.dirname(excluded_path), exist_ok=True)

    write_jsonl(args.data, kept)
    write_jsonl(excluded_path, excluded)

    print(
        f"LLM topic filter completed: kept {len(kept)}/{len(items)}, excluded {len(excluded)}",
        file=sys.stderr,
    )
    print(f"LLM topic filter excluded file: {excluded_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
