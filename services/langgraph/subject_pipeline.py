import time
import json
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from database import supabase
from config import settings
import anthropic

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ─── State Definition ─────────────────────────────────────────────────────────

class SubjectState(TypedDict):
    teacher_id: str
    school_id: str
    teacher_name: str
    triggered_by: str

    # Data loaded
    teacher_history: List[dict]
    available_subjects: List[str]
    school_needs: dict

    # Analysis
    performance_by_subject: dict

    # Output
    recommendations: List[dict]

    # Timing
    node_latencies: dict
    total_tokens: int
    cost_usd: float
    status: str
    error: Optional[str]

# ─── Node 1: Load Teacher History ─────────────────────────────────────────────

def load_teacher_history(state: SubjectState) -> SubjectState:
    start = time.time()
    print(f"[Subject Node 1] Loading teacher history for {state['teacher_id']}")

    # Get all observations grouped by subject
    obs_result = supabase.table("observations")\
        .select("subject,rating,strengths,improvements,observation_date")\
        .eq("teacher_id", state["teacher_id"])\
        .eq("status", "completed")\
        .execute()

    # Get grades by subject
    grades_result = supabase.table("grades")\
        .select("subject,score,grade_period")\
        .eq("teacher_id", state["teacher_id"])\
        .execute()

    state["teacher_history"] = {
        "observations": obs_result.data or [],
        "grades": grades_result.data or []
    }

    # Extract unique subjects taught
    subjects_from_obs = set(
        o["subject"] for o in obs_result.data
        if o.get("subject")
    )
    subjects_from_grades = set(
        g["subject"] for g in grades_result.data
        if g.get("subject")
    )
    all_subjects = list(subjects_from_obs | subjects_from_grades)

    # Available subjects = all subjects in the school
    all_school_obs = supabase.table("observations")\
        .select("subject")\
        .eq("school_id", state["school_id"])\
        .execute()

    school_subjects = list(set(
        o["subject"] for o in all_school_obs.data
        if o.get("subject")
    ))

    state["available_subjects"] = school_subjects if school_subjects else all_subjects
    state["node_latencies"]["load_teacher_history"] = round((time.time() - start) * 1000)

    print(f"[Subject Node 1] ✅ Found history across {len(all_subjects)} subjects")
    return state

# ─── Node 2: Analyze Subject Performance ──────────────────────────────────────

def analyze_subject_performance(state: SubjectState) -> SubjectState:
    start = time.time()
    print(f"[Subject Node 2] Analyzing performance by subject")

    obs = state["teacher_history"]["observations"]
    grades = state["teacher_history"]["grades"]
    performance = {}

    # Group observations by subject
    for o in obs:
        subject = o.get("subject", "Unknown")
        if subject not in performance:
            performance[subject] = {
                "ratings": [],
                "scores": [],
                "strengths": [],
                "improvements": [],
                "obs_count": 0
            }
        if o.get("rating"):
            performance[subject]["ratings"].append(o["rating"])
        if o.get("strengths"):
            performance[subject]["strengths"].append(o["strengths"][:100])
        if o.get("improvements"):
            performance[subject]["improvements"].append(o["improvements"][:100])
        performance[subject]["obs_count"] += 1

    # Group grades by subject
    for g in grades:
        subject = g.get("subject", "Unknown")
        if subject not in performance:
            performance[subject] = {
                "ratings": [],
                "scores": [],
                "strengths": [],
                "improvements": [],
                "obs_count": 0
            }
        if g.get("score"):
            performance[subject]["scores"].append(g["score"])

    # Calculate averages
    for subject in performance:
        ratings = performance[subject]["ratings"]
        scores = performance[subject]["scores"]
        performance[subject]["avg_rating"] = round(
            sum(ratings) / len(ratings), 2
        ) if ratings else None
        performance[subject]["avg_student_score"] = round(
            sum(scores) / len(scores), 1
        ) if scores else None

    state["performance_by_subject"] = performance
    state["node_latencies"]["analyze_subject_performance"] = round((time.time() - start) * 1000)

    print(f"[Subject Node 2] ✅ Analyzed {len(performance)} subjects")
    return state

# ─── Node 3: Load School Needs ────────────────────────────────────────────────

def load_school_needs(state: SubjectState) -> SubjectState:
    start = time.time()
    print(f"[Subject Node 3] Loading school staffing needs")

    # Count teachers per subject from observations
    all_obs = supabase.table("observations")\
        .select("subject,teacher_id")\
        .eq("school_id", state["school_id"])\
        .execute()

    subject_teacher_count = {}
    for o in all_obs.data or []:
        subject = o.get("subject")
        teacher = o.get("teacher_id")
        if subject and teacher:
            if subject not in subject_teacher_count:
                subject_teacher_count[subject] = set()
            subject_teacher_count[subject].add(teacher)

    # Convert to counts and priority
    needs = {}
    for subject, teachers in subject_teacher_count.items():
        count = len(teachers)
        if count <= 1:
            priority = "high"
        elif count <= 2:
            priority = "medium"
        else:
            priority = "low"
        needs[subject] = {
            "teacher_count": count,
            "priority": priority
        }

    state["school_needs"] = needs
    state["node_latencies"]["load_school_needs"] = round((time.time() - start) * 1000)

    print(f"[Subject Node 3] ✅ Loaded needs for {len(needs)} subjects")
    return state

# ─── Node 4: Generate Recommendations ────────────────────────────────────────

def generate_recommendations(state: SubjectState) -> SubjectState:
    start = time.time()
    print(f"[Subject Node 4] Generating AI subject recommendations")

    # Build performance summary for prompt
    perf_summary = []
    for subject, data in state["performance_by_subject"].items():
        perf_summary.append({
            "subject": subject,
            "avg_observation_rating": data.get("avg_rating"),
            "avg_student_score": data.get("avg_student_score"),
            "observation_count": data.get("obs_count", 0),
            "key_strengths": data.get("strengths", [])[:2],
            "key_improvements": data.get("improvements", [])[:2]
        })

    # Build needs summary
    needs_summary = [
        {
            "subject": s,
            "teacher_count": d["teacher_count"],
            "staffing_priority": d["priority"]
        }
        for s, d in state["school_needs"].items()
    ]

    prompt = f"""You are an expert school administrator making subject assignment recommendations.

Teacher: {state['teacher_name']}

Teacher's performance history by subject:
{json.dumps(perf_summary, indent=2)}

School staffing needs (fewer teachers = higher priority):
{json.dumps(needs_summary, indent=2)}

Available subjects for assignment:
{state['available_subjects']}

Generate ranked subject recommendations for this teacher.
Consider:
1. Teacher's performance ratings and student outcomes per subject
2. School's staffing needs and priorities
3. Growth potential based on strengths and improvement areas

Return ONLY valid JSON in this exact format:
{{
  "recommendations": [
    {{
      "subject": "exact subject name",
      "fit_score": 85,
      "reasoning": "specific evidence-based reasoning in 1-2 sentences",
      "confidence": "high",
      "school_need_priority": "high",
      "key_strength": "one specific strength for this subject",
      "development_area": "one specific area to develop"
    }}
  ]
}}

Rules:
- fit_score is 0-100 based on performance + school need
- confidence is high/medium/low
- Include top 3 recommendations only
- Base reasoning on actual data provided
- If no history for a subject, base on transferable skills"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
        recommendations = data.get("recommendations", [])
    except Exception as e:
        print(f"[Subject Node 4] ⚠️ JSON parse error: {e}")
        recommendations = [{
            "subject": state["available_subjects"][0] if state["available_subjects"] else "Unknown",
            "fit_score": 70,
            "reasoning": "Unable to parse AI response — manual review recommended",
            "confidence": "low",
            "school_need_priority": "medium",
            "key_strength": "See observation data",
            "development_area": "See observation data"
        }]

    state["recommendations"] = recommendations
    state["total_tokens"] = response.usage.input_tokens + response.usage.output_tokens
    state["cost_usd"] = round(
        (response.usage.input_tokens * 0.000003) +
        (response.usage.output_tokens * 0.000015), 6
    )
    state["status"] = "completed"
    state["node_latencies"]["generate_recommendations"] = round((time.time() - start) * 1000)

    print(f"[Subject Node 4] ✅ Generated {len(recommendations)} recommendations")
    for r in recommendations:
        print(f"  → {r['subject']}: {r['fit_score']}% fit")
    return state

# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_subject_graph():
    graph = StateGraph(SubjectState)

    graph.add_node("load_teacher_history", load_teacher_history)
    graph.add_node("analyze_subject_performance", analyze_subject_performance)
    graph.add_node("load_school_needs", load_school_needs)
    graph.add_node("generate_recommendations", generate_recommendations)

    graph.set_entry_point("load_teacher_history")
    graph.add_edge("load_teacher_history", "analyze_subject_performance")
    graph.add_edge("analyze_subject_performance", "load_school_needs")
    graph.add_edge("load_school_needs", "generate_recommendations")
    graph.add_edge("generate_recommendations", END)

    return graph.compile()

subject_app = build_subject_graph()