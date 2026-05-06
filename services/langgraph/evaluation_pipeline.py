import time
import json
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from database import supabase
from config import settings
import anthropic

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ─── State Definition ─────────────────────────────────────────────────────────

class EvaluationState(TypedDict):
    run_id: str
    teacher_id: str
    generated_review: str
    source_data: dict  # observations, goals, grades used to generate

    # Scores
    rubric_scores: dict
    hallucination_flags: List[str]
    consistency_issues: List[str]
    review_quality_score: float
    factual_consistency_score: float
    overall_eval_score: float

    # Timing
    node_latencies: dict
    eval_tokens: int
    status: str
    error: Optional[str]

# ─── Node 1: Rubric Scoring ───────────────────────────────────────────────────

def rubric_scoring(state: EvaluationState) -> EvaluationState:
    start = time.time()
    print(f"[Eval Node 1] Running rubric scoring")

    review = state["generated_review"]

    prompt = f"""You are an expert evaluator of teacher performance reviews.
Score this review on each criterion from 0.0 to 1.0:

REVIEW TO EVALUATE:
{review}

Score these criteria:
1. has_overall_assessment — Does it have a clear overall assessment section?
2. has_specific_evidence — Does it cite specific evidence from observations?
3. has_recommendations — Does it include actionable recommendations?
4. has_goals — Does it suggest specific goals?
5. professional_tone — Is the language professional and constructive?
6. specificity — Are claims specific rather than generic?
7. balanced_feedback — Does it address both strengths and improvements?

Return ONLY valid JSON:
{{
  "has_overall_assessment": 0.0,
  "has_specific_evidence": 0.0,
  "has_recommendations": 0.0,
  "has_goals": 0.0,
  "professional_tone": 0.0,
  "specificity": 0.0,
  "balanced_feedback": 0.0,
  "reasoning": "brief explanation"
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text
        # Clean JSON if wrapped in markdown
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        scores = json.loads(text.strip())
    except Exception:
        scores = {
            "has_overall_assessment": 0.5,
            "has_specific_evidence": 0.5,
            "has_recommendations": 0.5,
            "has_goals": 0.5,
            "professional_tone": 0.5,
            "specificity": 0.5,
            "balanced_feedback": 0.5,
            "reasoning": "Could not parse scores"
        }

    state["rubric_scores"] = scores
    state["eval_tokens"] = response.usage.input_tokens + response.usage.output_tokens
    state["node_latencies"]["rubric_scoring"] = round((time.time() - start) * 1000)

    numeric_scores = {k: v for k, v in scores.items()
                     if k != "reasoning" and isinstance(v, (int, float))}
    avg = sum(numeric_scores.values()) / len(numeric_scores) if numeric_scores else 0
    state["review_quality_score"] = round(avg, 2)

    print(f"[Eval Node 1] ✅ Review quality score: {state['review_quality_score']}")
    return state

# ─── Node 2: Hallucination Check ─────────────────────────────────────────────

def hallucination_check(state: EvaluationState) -> EvaluationState:
    start = time.time()
    print(f"[Eval Node 2] Running hallucination check")

    review = state["generated_review"]
    source = state["source_data"]

    obs_text = "\n".join([
        f"- Rating: {o.get('rating')}/5, Strengths: {o.get('strengths','')[:100]}, "
        f"Improvements: {o.get('improvements','')[:100]}"
        for o in source.get("observations", [])
    ]) or "No observations available"

    goals_text = "\n".join([
        f"- {g.get('title','')}: {g.get('progress',0)}% progress, status: {g.get('status','')}"
        for g in source.get("goals", [])
    ]) or "No goals available"

    grades_text = "\n".join([
        f"- {g.get('subject','')}: score {g.get('score','')}"
        for g in source.get("grade_trends", [])
    ]) or "No grade data available"

    prompt = f"""You are a fact-checker for teacher performance reviews.

SOURCE DATA (what was actually observed):
Observations:
{obs_text}

Goals:
{goals_text}

Grades:
{grades_text}

GENERATED REVIEW:
{review}

Check if the review makes any claims NOT supported by the source data.
Look for:
- Specific numbers that don't match source data
- Events or qualities not mentioned in observations
- Goal completion claims that contradict the data
- Student outcome claims without grade evidence

Return ONLY valid JSON:
{{
  "hallucination_flags": ["list any unsupported claims here, or empty list if none"],
  "factual_consistency_score": 0.0,
  "explanation": "brief explanation"
}}

factual_consistency_score: 1.0 = fully consistent, 0.0 = major hallucinations"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
    except Exception:
        result = {
            "hallucination_flags": [],
            "factual_consistency_score": 0.7,
            "explanation": "Could not parse"
        }

    state["hallucination_flags"] = result.get("hallucination_flags", [])
    state["factual_consistency_score"] = result.get("factual_consistency_score", 0.7)
    state["eval_tokens"] += response.usage.input_tokens + response.usage.output_tokens
    state["node_latencies"]["hallucination_check"] = round((time.time() - start) * 1000)

    print(f"[Eval Node 2] ✅ Factual consistency: {state['factual_consistency_score']}")
    if state["hallucination_flags"]:
        for flag in state["hallucination_flags"]:
            print(f"[Eval Node 2] ⚠️  {flag}")
    return state

# ─── Node 3: Consistency Check ────────────────────────────────────────────────

def consistency_check(state: EvaluationState) -> EvaluationState:
    start = time.time()
    print(f"[Eval Node 3] Running consistency check")

    review = state["generated_review"]
    issues = []

    # Simple rule-based consistency checks
    review_lower = review.lower()

    # Check for contradictions
    if "exceptional" in review_lower and "needs improvement" in review_lower:
        if review_lower.index("exceptional") < review_lower.index("needs improvement"):
            issues.append("Review calls performance exceptional then immediately notes needs improvement — check context")

    # Check rating vs language alignment
    source = state["source_data"]
    obs = source.get("observations", [])
    if obs:
        ratings = [o.get("rating", 0) for o in obs if o.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0

        if avg_rating >= 4.5 and "below expectations" in review_lower:
            issues.append("High observation ratings but review mentions 'below expectations'")
        if avg_rating <= 2.5 and "excellent" in review_lower:
            issues.append("Low observation ratings but review uses 'excellent' without qualification")

    # Check recommendation count
    rec_count = review_lower.count("recommendation") + review.count("1.") + review.count("2.")
    if rec_count == 0:
        issues.append("No clear recommendations found in review")

    state["consistency_issues"] = issues
    state["node_latencies"]["consistency_check"] = round((time.time() - start) * 1000)

    print(f"[Eval Node 3] ✅ Consistency issues found: {len(issues)}")
    return state

# ─── Node 4: Final Quality Score ─────────────────────────────────────────────

def final_quality_score(state: EvaluationState) -> EvaluationState:
    start = time.time()
    print(f"[Eval Node 4] Calculating final quality score")

    # Weighted combination
    quality_weight = 0.4
    consistency_weight = 0.4
    penalty_weight = 0.2

    # Penalty for issues found
    issue_count = len(state["hallucination_flags"]) + len(state["consistency_issues"])
    penalty = min(issue_count * 0.1, 0.3)  # max 0.3 penalty

    overall = (
        state["review_quality_score"] * quality_weight +
        state["factual_consistency_score"] * consistency_weight +
        (1 - penalty) * penalty_weight
    )

    state["overall_eval_score"] = round(overall, 2)
    state["status"] = "completed"
    state["node_latencies"]["final_quality_score"] = round((time.time() - start) * 1000)

    print(f"[Eval Node 4] ✅ Overall eval score: {state['overall_eval_score']}")
    return state

# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_evaluation_graph():
    graph = StateGraph(EvaluationState)

    graph.add_node("rubric_scoring", rubric_scoring)
    graph.add_node("hallucination_check", hallucination_check)
    graph.add_node("consistency_check", consistency_check)
    graph.add_node("final_quality_score", final_quality_score)

    graph.set_entry_point("rubric_scoring")
    graph.add_edge("rubric_scoring", "hallucination_check")
    graph.add_edge("hallucination_check", "consistency_check")
    graph.add_edge("consistency_check", "final_quality_score")
    graph.add_edge("final_quality_score", END)

    return graph.compile()

evaluation_app = build_evaluation_graph()