import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from dependencies import role_required, get_current_user
from database import supabase
from services.langgraph.review_pipeline import review_app
import json
import asyncio
from services.langgraph.evaluation_pipeline import evaluation_app, EvaluationState
from services.langgraph.subject_pipeline import subject_app

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

class PipelineRequest(BaseModel):
    teacher_id: str

@router.post("/run-review")
async def run_review_pipeline(
    body: PipelineRequest,
    current_user = Depends(role_required("admin"))
):
    # Verify teacher exists
    teacher = supabase.table("users")\
        .select("*")\
        .eq("id", body.teacher_id)\
        .eq("role", "teacher")\
        .execute()

    if not teacher.data:
        raise HTTPException(status_code=404, detail="Teacher not found")

    teacher_data = teacher.data[0]

    # Create pipeline run record
    run_id = str(uuid.uuid4())
    supabase.table("pipeline_runs").insert({
        "id": run_id,
        "teacher_id": body.teacher_id,
        "triggered_by": current_user["id"],
        "run_type": "review_generation",
        "status": "running"
    }).execute()

    async def generate():
        pipeline_start = time.time()

        try:
            # Stream node progress to frontend
            yield f"data: {json.dumps({'event': 'start', 'run_id': run_id, 'teacher': teacher_data['full_name']})}\n\n"

            # Initialize state
            initial_state = {
                "teacher_id": body.teacher_id,
                "school_id": current_user["school_id"],
                "teacher_name": teacher_data["full_name"],
                "triggered_by": current_user["id"],
                "run_id": run_id,
                "observations": [],
                "goals": [],
                "grade_trends": [],
                "completeness_score": 0.0,
                "data_warnings": [],
                "missing_fields": [],
                "analysis": {},
                "generated_review": "",
                "confidence_score": 0.0,
                "risk_flags": [],
                "node_latencies": {},
                "total_tokens": 0,
                "cost_usd": 0.0,
                "status": "running",
                "error": None
            }

            # Stream node updates
            nodes = [
                "load_observations",
                "load_goals",
                "load_grade_trends",
                "data_quality_check",
                "analyze_performance",
                "generate_review",
                "confidence_scoring"
            ]

            node_labels = {
                "load_observations": "Loading observation history",
                "load_goals": "Loading goal progress",
                "load_grade_trends": "Loading grade trends",
                "data_quality_check": "Running data quality check",
                "analyze_performance": "Analyzing performance patterns",
                "generate_review": "Generating AI review with Claude",
                "confidence_scoring": "Calculating confidence scores"
            }

            for node in nodes:
                yield f"data: {json.dumps({'event': 'node_start', 'node': node, 'label': node_labels[node]})}\n\n"
                await asyncio.sleep(0.1)

            # Run the full pipeline
            result = review_app.invoke(initial_state)

            total_latency = round((time.time() - pipeline_start) * 1000)

            # Save results to database
            supabase.table("pipeline_runs").update({
                "completeness_score": result["completeness_score"],
                "data_warnings": result["data_warnings"],
                "confidence_score": result["confidence_score"],
                "risk_flags": result["risk_flags"],
                "generated_review": result["generated_review"],
                "total_latency_ms": total_latency,
                "node_latencies": result["node_latencies"],
                "total_tokens": result["total_tokens"],
                "cost_usd": result["cost_usd"],
                "status": "completed"
            }).eq("id", run_id).execute()

            # Stream final result
            yield f"data: {json.dumps({'event': 'complete', 'run_id': run_id, 'result': {'review': result['generated_review'], 'confidence_score': result['confidence_score'], 'completeness_score': result['completeness_score'], 'risk_flags': result['risk_flags'], 'data_warnings': result['data_warnings'], 'node_latencies': result['node_latencies'], 'total_tokens': result['total_tokens'], 'cost_usd': result['cost_usd'], 'total_latency_ms': total_latency}})}\n\n"

        except Exception as e:
            # Save failure to database
            supabase.table("pipeline_runs").update({
                "status": "failed",
                "error": str(e) if hasattr(e, '__str__') else "Unknown error"
            }).eq("id", run_id).execute()

            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/status/{run_id}")
async def get_pipeline_status(
    run_id: str,
    current_user = Depends(get_current_user)
):
    result = supabase.table("pipeline_runs")\
        .select("*")\
        .eq("id", run_id)\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    return result.data[0]

@router.get("/runs/{teacher_id}")
async def get_pipeline_runs(
    teacher_id: str,
    current_user = Depends(role_required("admin"))
):
    result = supabase.table("pipeline_runs")\
        .select("*")\
        .eq("teacher_id", teacher_id)\
        .order("created_at", desc=True)\
        .limit(10)\
        .execute()

    return {"data": result.data}

@router.get("/metrics/{teacher_id}")
async def get_teacher_metrics(
    teacher_id: str,
    current_user = Depends(role_required("admin"))
):
    result = supabase.table("pipeline_runs")\
        .select("*")\
        .eq("teacher_id", teacher_id)\
        .eq("status", "completed")\
        .execute()

    runs = result.data or []

    if not runs:
        return {"message": "No completed pipeline runs found"}

    avg_confidence = sum(r["confidence_score"] for r in runs if r.get("confidence_score")) / len(runs)
    avg_latency = sum(r["total_latency_ms"] for r in runs if r.get("total_latency_ms")) / len(runs)
    total_cost = sum(r["cost_usd"] for r in runs if r.get("cost_usd"))
    total_tokens = sum(r["total_tokens"] for r in runs if r.get("total_tokens"))

    return {
        "total_runs": len(runs),
        "avg_confidence_score": round(avg_confidence, 2),
        "avg_latency_ms": round(avg_latency),
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens
    }

@router.post("/evaluate/{run_id}")
async def evaluate_review(
    run_id: str,
    current_user = Depends(role_required("admin"))
):
    # Get the pipeline run
    run_result = supabase.table("pipeline_runs")\
        .select("*")\
        .eq("id", run_id)\
        .execute()

    if not run_result.data:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    run = run_result.data[0]

    if not run.get("generated_review"):
        raise HTTPException(
            status_code=400,
            detail="No review generated yet — run the pipeline first"
        )

    # Get source data for hallucination check
    obs = supabase.table("observations")\
        .select("*")\
        .eq("teacher_id", run["teacher_id"])\
        .eq("status", "completed")\
        .execute()

    goals = supabase.table("goals")\
        .select("*")\
        .eq("staff_id", run["teacher_id"])\
        .execute()

    grades = supabase.table("grades")\
        .select("*")\
        .eq("teacher_id", run["teacher_id"])\
        .execute()

    async def generate():
        yield f"data: {json.dumps({'event': 'eval_start', 'run_id': run_id})}\n\n"

        eval_nodes = [
            ("rubric_scoring", "Scoring review against rubric"),
            ("hallucination_check", "Checking factual consistency"),
            ("consistency_check", "Checking internal consistency"),
            ("final_quality_score", "Calculating final quality score")
        ]

        for node, label in eval_nodes:
            yield f"data: {json.dumps({'event': 'eval_node', 'node': node, 'label': label})}\n\n"
            await asyncio.sleep(0.1)

        try:
            initial_state = {
                "run_id": run_id,
                "teacher_id": run["teacher_id"],
                "generated_review": run["generated_review"],
                "source_data": {
                    "observations": obs.data or [],
                    "goals": goals.data or [],
                    "grade_trends": grades.data or []
                },
                "rubric_scores": {},
                "hallucination_flags": [],
                "consistency_issues": [],
                "review_quality_score": 0.0,
                "factual_consistency_score": 0.0,
                "overall_eval_score": 0.0,
                "node_latencies": {},
                "eval_tokens": 0,
                "status": "running",
                "error": None
            }

            result = evaluation_app.invoke(initial_state)

            # Save evaluation results
            supabase.table("pipeline_runs").update({
                "review_quality_score": result["review_quality_score"],
                "factual_consistency_score": result["factual_consistency_score"],
                "evaluation_results": {
                    "overall_eval_score": result["overall_eval_score"],
                    "rubric_scores": result["rubric_scores"],
                    "hallucination_flags": result["hallucination_flags"],
                    "consistency_issues": result["consistency_issues"],
                    "node_latencies": result["node_latencies"],
                    "eval_tokens": result["eval_tokens"]
                }
            }).eq("id", run_id).execute()

            yield f"data: {json.dumps({'event': 'eval_complete', 'result': {'overall_eval_score': result['overall_eval_score'], 'review_quality_score': result['review_quality_score'], 'factual_consistency_score': result['factual_consistency_score'], 'hallucination_flags': result['hallucination_flags'], 'consistency_issues': result['consistency_issues'], 'rubric_scores': result['rubric_scores']}})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'event': 'eval_error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@router.get("/evaluation/{run_id}")
async def get_evaluation(
    run_id: str,
    current_user = Depends(role_required("admin"))
):
    result = supabase.table("pipeline_runs")\
        .select("id,review_quality_score,factual_consistency_score,evaluation_results,confidence_score")\
        .eq("id", run_id)\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Not found")

    return result.data[0]

@router.post("/subject-recommendation/{teacher_id}")
async def run_subject_recommendation(
    teacher_id: str,
    current_user = Depends(role_required("admin"))
):
    # Verify teacher exists
    teacher = supabase.table("users")\
        .select("*")\
        .eq("id", teacher_id)\
        .eq("role", "teacher")\
        .execute()

    if not teacher.data:
        raise HTTPException(status_code=404, detail="Teacher not found")

    teacher_data = teacher.data[0]

    async def generate():
        yield f"data: {json.dumps({'event': 'start', 'teacher': teacher_data['full_name']})}\n\n"

        nodes = [
            ("load_teacher_history", "Loading subject history"),
            ("analyze_subject_performance", "Analyzing performance by subject"),
            ("load_school_needs", "Loading school staffing needs"),
            ("generate_recommendations", "Generating AI recommendations")
        ]

        for node, label in nodes:
            yield f"data: {json.dumps({'event': 'node_start', 'node': node, 'label': label})}\n\n"
            await asyncio.sleep(0.1)

        try:
            initial_state = {
                "teacher_id": teacher_id,
                "school_id": current_user["school_id"],
                "teacher_name": teacher_data["full_name"],
                "triggered_by": current_user["id"],
                "teacher_history": {},
                "available_subjects": [],
                "school_needs": {},
                "performance_by_subject": {},
                "recommendations": [],
                "node_latencies": {},
                "total_tokens": 0,
                "cost_usd": 0.0,
                "status": "running",
                "error": None
            }

            result = subject_app.invoke(initial_state)

            # Save to subject_recommendations table
            supabase.table("subject_recommendations").insert({
                "school_id": current_user["school_id"],
                "teacher_id": teacher_id,
                "generated_by": current_user["id"],
                "recommendations": result["recommendations"]
            }).execute()

            yield f"data: {json.dumps({'event': 'complete', 'result': {'teacher': teacher_data['full_name'], 'recommendations': result['recommendations'], 'node_latencies': result['node_latencies'], 'total_tokens': result['total_tokens'], 'cost_usd': result['cost_usd']}})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@router.get("/subject-recommendation/{teacher_id}/latest")
async def get_latest_recommendation(
    teacher_id: str,
    current_user = Depends(role_required("admin"))
):
    result = supabase.table("subject_recommendations")\
        .select("*")\
        .eq("teacher_id", teacher_id)\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()

    if not result.data:
        return {"message": "No recommendations generated yet"}

    return result.data[0]