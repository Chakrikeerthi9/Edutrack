import time
import json
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from database import supabase
from config import settings
import anthropic

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ─── State Definition ───────────────────────────────────────────────────────

class ReviewState(TypedDict):
    teacher_id: str
    school_id: str
    teacher_name: str
    triggered_by: str
    run_id: str

    # Data loaded
    observations: List[dict]
    goals: List[dict]
    grade_trends: List[dict]

    # Quality check
    completeness_score: float
    data_warnings: List[str]
    missing_fields: List[str]

    # Analysis
    analysis: dict

    # Output
    generated_review: str
    confidence_score: float
    risk_flags: List[str]

    # Timing
    node_latencies: dict
    total_tokens: int
    cost_usd: float
    status: str
    error: Optional[str]

# ─── Node 1: Load Observations ───────────────────────────────────────────────

def load_observations(state: ReviewState) -> ReviewState:
    start = time.time()
    print(f"[Node 1] Loading observations for teacher {state['teacher_id']}")

    result = supabase.table("observations")\
        .select("*")\
        .eq("teacher_id", state["teacher_id"])\
        .eq("status", "completed")\
        .order("observation_date", desc=True)\
        .execute()

    state["observations"] = result.data or []
    state["node_latencies"]["load_observations"] = round((time.time() - start) * 1000)
    print(f"[Node 1] ✅ Loaded {len(state['observations'])} observations")
    return state

# ─── Node 2: Load Goals ───────────────────────────────────────────────────────

def load_goals(state: ReviewState) -> ReviewState:
    start = time.time()
    print(f"[Node 2] Loading goals for teacher {state['teacher_id']}")

    result = supabase.table("goals")\
        .select("*")\
        .eq("staff_id", state["teacher_id"])\
        .order("target_date")\
        .execute()

    state["goals"] = result.data or []
    state["node_latencies"]["load_goals"] = round((time.time() - start) * 1000)
    print(f"[Node 2] ✅ Loaded {len(state['goals'])} goals")
    return state

# ─── Node 3: Load Grade Trends ────────────────────────────────────────────────

def load_grade_trends(state: ReviewState) -> ReviewState:
    start = time.time()
    print(f"[Node 3] Loading grade trends for teacher {state['teacher_id']}")

    result = supabase.table("grades")\
        .select("subject,grade_period,score,grade_letter")\
        .eq("teacher_id", state["teacher_id"])\
        .order("grade_period", desc=True)\
        .execute()

    state["grade_trends"] = result.data or []
    state["node_latencies"]["load_grade_trends"] = round((time.time() - start) * 1000)
    print(f"[Node 3] ✅ Loaded {len(state['grade_trends'])} grade records")
    return state

# ─── Node 4: Data Quality Check ───────────────────────────────────────────────

def data_quality_check(state: ReviewState) -> ReviewState:
    start = time.time()
    print(f"[Node 4] Running data quality check")

    warnings = []
    missing = []
    score_components = []

    # Check observations
    if len(state["observations"]) == 0:
        warnings.append("No completed observations found")
        missing.append("observations")
        score_components.append(0)
    elif len(state["observations"]) < 2:
        warnings.append("Only 1 observation — low confidence in patterns")
        score_components.append(0.5)
    else:
        score_components.append(1.0)

    # Check goals
    if len(state["goals"]) == 0:
        warnings.append("No goals found for this teacher")
        missing.append("goals")
        score_components.append(0)
    else:
        score_components.append(1.0)

    # Check grade trends
    if len(state["grade_trends"]) == 0:
        warnings.append("No grade data available — cannot assess student outcomes")
        missing.append("grade_trends")
        score_components.append(0.3)
    else:
        score_components.append(1.0)

    # Check observation quality
    obs_with_strengths = [o for o in state["observations"] if o.get("strengths")]
    obs_with_improvements = [o for o in state["observations"] if o.get("improvements")]

    if len(obs_with_strengths) < len(state["observations"]):
        warnings.append("Some observations missing strengths field")
        score_components.append(0.7)
    else:
        score_components.append(1.0)

    # Calculate completeness score
    completeness = sum(score_components) / len(score_components) if score_components else 0

    state["completeness_score"] = round(completeness, 2)
    state["data_warnings"] = warnings
    state["missing_fields"] = missing
    state["node_latencies"]["data_quality_check"] = round((time.time() - start) * 1000)

    print(f"[Node 4] ✅ Completeness score: {completeness:.2f}")
    if warnings:
        for w in warnings:
            print(f"[Node 4] ⚠️  {w}")

    return state

# ─── Node 5: Performance Analysis ────────────────────────────────────────────

def analyze_performance(state: ReviewState) -> ReviewState:
    start = time.time()
    print(f"[Node 5] Analyzing performance data")

    obs = state["observations"]
    goals = state["goals"]
    grades = state["grade_trends"]

    # Observation metrics
    ratings = [o["rating"] for o in obs if o.get("rating")]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0

    # Goal metrics
    completed_goals = [g for g in goals if g["status"] == "completed"]
    active_goals = [g for g in goals if g["status"] == "active"]
    goal_completion_rate = len(completed_goals) / len(goals) if goals else 0

    avg_progress = sum(g.get("progress", 0) for g in active_goals) / len(active_goals) \
                   if active_goals else 0

    # Grade metrics
    scores = [g["score"] for g in grades if g.get("score")]
    avg_student_score = round(sum(scores) / len(scores), 1) if scores else None

    # Collect key evidence
    key_strengths = []
    key_improvements = []
    for o in obs[:3]:
        if o.get("strengths"):
            key_strengths.append(o["strengths"][:150])
        if o.get("improvements"):
            key_improvements.append(o["improvements"][:150])

    state["analysis"] = {
        "avg_observation_rating": avg_rating,
        "observation_count": len(obs),
        "goal_completion_rate": round(goal_completion_rate, 2),
        "avg_goal_progress": round(avg_progress, 1),
        "avg_student_score": avg_student_score,
        "completed_goals": len(completed_goals),
        "total_goals": len(goals),
        "key_strengths": key_strengths,
        "key_improvements": key_improvements,
        "subjects_taught": list(set(g["subject"] for g in grades if g.get("subject")))
    }

    state["node_latencies"]["analyze_performance"] = round((time.time() - start) * 1000)
    print(f"[Node 5] ✅ Avg rating: {avg_rating}, Goal completion: {goal_completion_rate:.0%}")
    return state

# ─── Node 6: Generate Review ─────────────────────────────────────────────────

def generate_review(state: ReviewState) -> ReviewState:
    start = time.time()
    print(f"[Node 6] Generating AI review with Claude")

    a = state["analysis"]
    warnings_text = "\n".join(state["data_warnings"]) if state["data_warnings"] else "None"

    prompt = f"""You are an expert K-12 school administrator generating a professional teacher performance review.

Teacher: {state['teacher_name']}
Data completeness: {state['completeness_score']:.0%}
Data warnings: {warnings_text}

Performance Data:
- Average observation rating: {a['avg_observation_rating']}/5 across {a['observation_count']} observations
- Goal completion rate: {a['goal_completion_rate']:.0%} ({a['completed_goals']} of {a['total_goals']} goals)
- Average goal progress: {a['avg_goal_progress']:.0f}%
- Average student score: {a['avg_student_score'] if a['avg_student_score'] else 'No data'}
- Subjects taught: {', '.join(a['subjects_taught']) if a['subjects_taught'] else 'Unknown'}

Key strengths from observations:
{chr(10).join(f'- {s}' for s in a['key_strengths']) if a['key_strengths'] else '- Insufficient data'}

Development areas from observations:
{chr(10).join(f'- {i}' for i in a['key_improvements']) if a['key_improvements'] else '- Insufficient data'}

Generate a structured professional performance review with these sections:
1. OVERALL ASSESSMENT (2-3 sentences, evidence-based)
2. INSTRUCTIONAL EFFECTIVENESS (specific, cite observation evidence)
3. PROFESSIONAL DEVELOPMENT (reference goal progress)
4. STUDENT OUTCOMES (reference grade data if available)
5. RECOMMENDATIONS (3 specific, actionable items for next period)
6. SUGGESTED GOALS (2 concrete goals for upcoming semester)

If data is limited, acknowledge it professionally and base assessment on available evidence only.
Be specific, fair, and constructive. Avoid generic statements."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    state["generated_review"] = response.content[0].text
    state["total_tokens"] = response.usage.input_tokens + response.usage.output_tokens
    state["cost_usd"] = round(
        (response.usage.input_tokens * 0.000003) +
        (response.usage.output_tokens * 0.000015), 6
    )

    state["node_latencies"]["generate_review"] = round((time.time() - start) * 1000)
    print(f"[Node 6] ✅ Review generated — {state['total_tokens']} tokens, ${state['cost_usd']}")
    return state

# ─── Node 7: Confidence + Risk Scoring ───────────────────────────────────────

def confidence_scoring(state: ReviewState) -> ReviewState:
    start = time.time()
    print(f"[Node 7] Calculating confidence and risk scores")

    risk_flags = []
    confidence_components = []

    # Base confidence on data completeness
    confidence_components.append(state["completeness_score"])

    # Observation quantity confidence
    obs_count = len(state["observations"])
    if obs_count >= 3:
        confidence_components.append(1.0)
    elif obs_count == 2:
        confidence_components.append(0.7)
        risk_flags.append("Limited observation sample — consider additional visits")
    elif obs_count == 1:
        confidence_components.append(0.4)
        risk_flags.append("Single observation — review may not represent full performance")
    else:
        confidence_components.append(0.1)
        risk_flags.append("No observations — review based on insufficient data")

    # Goal data confidence
    if len(state["goals"]) >= 3:
        confidence_components.append(1.0)
    elif len(state["goals"]) > 0:
        confidence_components.append(0.7)
    else:
        confidence_components.append(0.2)
        risk_flags.append("No goals data — professional development cannot be assessed")

    # Grade data confidence
    if len(state["grade_trends"]) >= 5:
        confidence_components.append(1.0)
    elif len(state["grade_trends"]) > 0:
        confidence_components.append(0.6)
    else:
        confidence_components.append(0.3)
        risk_flags.append("No student grade data — outcomes assessment limited")

    # Rating consistency check
    ratings = [o["rating"] for o in state["observations"] if o.get("rating")]
    if len(ratings) >= 2:
        rating_variance = max(ratings) - min(ratings)
        if rating_variance >= 2:
            risk_flags.append("High variance in observation ratings — inconsistent performance pattern")
            confidence_components.append(0.6)
        else:
            confidence_components.append(1.0)

    # Final confidence score
    confidence = sum(confidence_components) / len(confidence_components)
    state["confidence_score"] = round(confidence, 2)
    state["risk_flags"] = risk_flags
    state["status"] = "completed"

    state["node_latencies"]["confidence_scoring"] = round((time.time() - start) * 1000)
    print(f"[Node 7] ✅ Confidence: {confidence:.2f}, Risk flags: {len(risk_flags)}")
    return state

# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_review_graph():
    graph = StateGraph(ReviewState)

    graph.add_node("load_observations", load_observations)
    graph.add_node("load_goals", load_goals)
    graph.add_node("load_grade_trends", load_grade_trends)
    graph.add_node("data_quality_check", data_quality_check)
    graph.add_node("analyze_performance", analyze_performance)
    graph.add_node("generate_review", generate_review)
    graph.add_node("confidence_scoring", confidence_scoring)

    graph.set_entry_point("load_observations")
    graph.add_edge("load_observations", "load_goals")
    graph.add_edge("load_goals", "load_grade_trends")
    graph.add_edge("load_grade_trends", "data_quality_check")
    graph.add_edge("data_quality_check", "analyze_performance")
    graph.add_edge("analyze_performance", "generate_review")
    graph.add_edge("generate_review", "confidence_scoring")
    graph.add_edge("confidence_scoring", END)

    return graph.compile()

review_app = build_review_graph()