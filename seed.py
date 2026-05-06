import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client
from passlib.context import CryptContext

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_ANON_KEY")
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def seed():
    print("🌱 Seeding database...")

    # 1. Insert school
    school = supabase.table("schools").insert({
        "name": "Westfield Academy",
        "address": "123 Education Blvd, Kansas City, MO"
    }).execute()

    school_id = school.data[0]["id"]
    print(f"✅ School created: {school_id}")

    # 2. Insert school settings
    supabase.table("school_settings").insert({
        "school_id": school_id,
        "feedback_to_teachers": True,
        "ai_features_enabled": True,
        "grade_sharing_enabled": True
    }).execute()
    print("✅ School settings created")

    # 3. Insert admin user
    admin = supabase.table("users").insert({
        "school_id": school_id,
        "email": "admin@westfield.edu",
        "password_hash": hash_password("admin123"),
        "full_name": "Sarah Anderson",
        "role": "admin",
        "department": "Administration"
    }).execute()
    print(f"✅ Admin created: admin@westfield.edu / admin123")

    # 4. Insert teachers
    teachers = [
        {
            "school_id": school_id,
            "email": "sarah.johnson@westfield.edu",
            "password_hash": hash_password("teacher123"),
            "full_name": "Sarah Johnson",
            "role": "teacher",
            "department": "Mathematics"
        },
        {
            "school_id": school_id,
            "email": "marcus.chen@westfield.edu",
            "password_hash": hash_password("teacher123"),
            "full_name": "Marcus Chen",
            "role": "teacher",
            "department": "Science"
        },
        {
            "school_id": school_id,
            "email": "aisha.thompson@westfield.edu",
            "password_hash": hash_password("teacher123"),
            "full_name": "Aisha Thompson",
            "role": "teacher",
            "department": "English"
        },
        {
            "school_id": school_id,
            "email": "james.park@westfield.edu",
            "password_hash": hash_password("teacher123"),
            "full_name": "James Park",
            "role": "teacher",
            "department": "History"
        }
    ]

    result = supabase.table("users").insert(teachers).execute()
    teacher_ids = [t["id"] for t in result.data]
    print(f"✅ {len(teachers)} teachers created")

    # 5. Insert observer
    observer = supabase.table("users").insert({
        "school_id": school_id,
        "email": "observer@westfield.edu",
        "password_hash": hash_password("observer123"),
        "full_name": "Maria Rivera",
        "role": "observer",
        "department": "Instructional Coaching"
    }).execute()
    print("✅ Observer created: observer@westfield.edu / observer123")

    # 6. Insert observations for Sarah Johnson
    observations = [
        {
            "school_id": school_id,
            "observer_id": observer.data[0]["id"],
            "teacher_id": teacher_ids[0],
            "subject": "Mathematics",
            "grade_level": "8th Grade",
            "observation_date": "2026-04-15",
            "strengths": "Strong questioning techniques throughout the lesson. Students showed high engagement with 87% on-task behavior observed during fraction division activity. Excellent use of visual aids.",
            "improvements": "Pacing could be improved in the latter half of the lesson. Some students appeared to disengage during independent practice time.",
            "rating": 4,
            "status": "completed"
        },
        {
            "school_id": school_id,
            "observer_id": observer.data[0]["id"],
            "teacher_id": teacher_ids[0],
            "subject": "Mathematics",
            "grade_level": "8th Grade",
            "observation_date": "2026-03-10",
            "strengths": "Clear learning objectives posted and referenced throughout. Good use of collaborative learning structures.",
            "improvements": "Differentiation for advanced learners needs attention. Several students finished early with no extension activity.",
            "rating": 3,
            "status": "completed"
        },
        {
            "school_id": school_id,
            "observer_id": observer.data[0]["id"],
            "teacher_id": teacher_ids[1],
            "subject": "Science",
            "grade_level": "7th Grade",
            "observation_date": "2026-04-20",
            "strengths": "Exceptional hands-on lab management. Students were fully engaged in the cell biology experiment. Safety protocols followed perfectly.",
            "improvements": "Could improve scientific vocabulary instruction for ELL students.",
            "rating": 5,
            "status": "completed"
        },
        {
            "school_id": school_id,
            "observer_id": observer.data[0]["id"],
            "teacher_id": teacher_ids[2],
            "subject": "English",
            "grade_level": "6th Grade",
            "observation_date": "2026-04-28",
            "strengths": "Good rapport with students. Creative writing prompts were engaging.",
            "improvements": "Classroom management during transitions needs work. Some students off-task for extended periods.",
            "rating": 3,
            "status": "submitted"
        }
    ]

    supabase.table("observations").insert(observations).execute()
    print(f"✅ {len(observations)} observations created")

    # 7. Insert goals
    goals = [
        {
            "school_id": school_id,
            "staff_id": teacher_ids[0],
            "title": "Complete 20hrs PD in math curriculum differentiation",
            "description": "Focus on differentiation strategies for mixed ability classrooms",
            "target_date": "2026-06-01",
            "progress": 78,
            "status": "active"
        },
        {
            "school_id": school_id,
            "staff_id": teacher_ids[2],
            "title": "Implement restorative practices in classroom management",
            "description": "Complete district restorative practices workshop and implement 3 strategies",
            "target_date": "2026-05-15",
            "progress": 45,
            "status": "active"
        },
        {
            "school_id": school_id,
            "staff_id": teacher_ids[1],
            "title": "Complete STEM certification program",
            "description": "Finish all modules in the district STEM certification pathway",
            "target_date": "2026-05-10",
            "progress": 95,
            "status": "active"
        },
        {
            "school_id": school_id,
            "staff_id": teacher_ids[3],
            "title": "Develop differentiation strategies workshop",
            "description": "Attend and implement strategies from district PD workshop",
            "target_date": "2026-06-30",
            "progress": 22,
            "status": "active"
        }
    ]

    supabase.table("goals").insert(goals).execute()
    print(f"✅ {len(goals)} goals created")

    # 8. Insert grades
    student = supabase.table("users").insert({
        "school_id": school_id,
        "email": "student@westfield.edu",
        "password_hash": hash_password("student123"),
        "full_name": "Alex Martinez",
        "role": "student",
        "department": "8th Grade"
    }).execute()

    grades = [
        {
            "school_id": school_id,
            "teacher_id": teacher_ids[0],
            "student_id": student.data[0]["id"],
            "subject": "Mathematics",
            "grade_period": "Q2 2026",
            "score": 87.5,
            "grade_letter": "B",
            "shared_with_student": True,
            "shared_with_admin": True
        },
        {
            "school_id": school_id,
            "teacher_id": teacher_ids[1],
            "student_id": student.data[0]["id"],
            "subject": "Science",
            "grade_period": "Q2 2026",
            "score": 94.0,
            "grade_letter": "A",
            "shared_with_student": True,
            "shared_with_admin": True
        }
    ]

    supabase.table("grades").insert(grades).execute()
    print(f"✅ Grades created")

    print("\n🎉 Seed complete!")
    print("\n📋 Login credentials:")
    print("  Admin:    admin@westfield.edu / admin123")
    print("  Teacher:  sarah.johnson@westfield.edu / teacher123")
    print("  Observer: observer@westfield.edu / observer123")
    print("  Student:  student@westfield.edu / student123")

seed()