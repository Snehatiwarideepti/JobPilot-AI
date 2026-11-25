"""
End-to-End Smoke Test:
Profile -> Search Jobs -> Job Details -> Analyze Match (V2) -> Skill Gaps -> Save Job.
"""
import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import AsyncSessionLocal
from app.models import Job
from sqlalchemy import select


async def smoke_test():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        test_uid = str(uuid.uuid4())
        print(f"=== STARTING END-TO-END SMOKE TEST (User ID: {test_uid}) ===\n")

        # 1. Profile: Create/Update Profile
        print("1. Testing Profile creation/update (POST /profile)...")
        profile_payload = {
            "full_name": "Jordan Lee",
            "email": "jordan.lee@example.com",
            "location": "New York, NY",
            "target_roles": ["Senior Engineer", "Software Engineer"],
            "remote_preference": "hybrid",
            "experience_level": "senior",
            "summary": "Senior software engineer with 6 years experience in Python, SQL, Azure, and microservices.",
            "skills": [
                {"name": "Python", "proficiency": "expert", "years_of_experience": 6.0},
                {"name": "SQL", "proficiency": "advanced", "years_of_experience": 5.0},
                {"name": "Azure", "proficiency": "intermediate", "years_of_experience": 3.0},
                {"name": "Docker", "proficiency": "intermediate", "years_of_experience": 3.0},
                {"name": "FastAPI", "proficiency": "advanced", "years_of_experience": 3.0},
            ],
            "projects": [
                {
                    "name": "Cloud ETL Pipeline",
                    "description": "Built an Azure data pipeline using Python, SQL, and Docker containerization.",
                    "technologies": ["Python", "SQL", "Azure", "Docker"],
                }
            ],
            "experience": [
                {
                    "company": "Tech Corp",
                    "title": "Senior Software Engineer",
                    "description": "Lead backend development using Python, FastAPI, and Azure.",
                    "technologies": ["Python", "FastAPI", "Azure"],
                    "is_current": True,
                }
            ],
            "education": [
                {
                    "institution": "Columbia University",
                    "degree": "B.S.",
                    "field_of_study": "Computer Science",
                }
            ],
        }
        res_prof = await client.post(f"/profile?user_id={test_uid}", json=profile_payload)
        print(f"   POST /profile status: {res_prof.status_code}")
        assert res_prof.status_code == 200, res_prof.text
        prof_data = res_prof.json()
        print(f"   Saved Profile: {prof_data.get('full_name')} with {len(prof_data.get('skills', []))} skills")

        # 2. Profile: Get Profile
        print("\n2. Testing GET /profile...")
        res_get_prof = await client.get(f"/profile?user_id={test_uid}")
        print(f"   GET /profile status: {res_get_prof.status_code}")
        assert res_get_prof.status_code == 200
        assert res_get_prof.json()["email"] == "jordan.lee@example.com"

        # 3. Retrieve Real Job from DB
        async with AsyncSessionLocal() as db:
            jobs = (await db.execute(select(Job))).scalars().all()
            assert len(jobs) >= 1, "No jobs in database"
            real_job = jobs[0]
            real_job_id = str(real_job.id)
            print(f"\n3. Selected Real Job from DB: {real_job_id} ({real_job.title})")

        # 4. Job Details
        print(f"\n4. Testing GET /jobs/{real_job_id}...")
        res_job = await client.get(f"/jobs/{real_job_id}")
        print(f"   GET /jobs/{real_job_id} status: {res_job.status_code}")
        assert res_job.status_code == 200
        job_details = res_job.json()
        print(f"   Title: {job_details.get('title')}, Company: {job_details.get('company')}")

        # 5. Analyze Match V2
        print(f"\n5. Testing GET /jobs/{real_job_id}/match/v2 (Core Milestone Requirement)...")
        res_match = await client.get(f"/jobs/{real_job_id}/match/v2?user_id={test_uid}")
        print(f"   GET /jobs/{real_job_id}/match/v2 status: {res_match.status_code}")
        assert res_match.status_code == 200, res_match.text
        match_data = res_match.json()
        print(f"   Overall Match Score: {match_data.get('overall_match_score')}/100")
        print(f"   Score Breakdown: {match_data.get('score_breakdown')}")
        print(f"   Recommendation: {match_data.get('recommendation')}")
        print(f"   Experience Fit: {match_data.get('experience_fit')}")
        print(f"   Workplace Fit: {match_data.get('workplace_fit')}")
        print(f"   Candidate Strengths: {match_data.get('candidate_strengths')}")
        print(f"   Matched Requirements: {len(match_data.get('matched_requirements', []))}")
        print(f"   Partial Matches: {len(match_data.get('partial_matches', []))}")
        print(f"   Gaps: {len(match_data.get('missing_requirements', []))}")
        print(f"   Unknowns: {len(match_data.get('unknown_requirements', []))}")
        print(f"   Reasoning: {match_data.get('reasoning')[:120]}...")

        # Verify all required V2 fields exist and are populated
        assert "overall_match_score" in match_data
        assert "score_breakdown" in match_data
        assert "experience_fit" in match_data
        assert "workplace_fit" in match_data
        assert "candidate_strengths" in match_data
        assert "matched_requirements" in match_data
        assert "partial_matches" in match_data
        assert "missing_requirements" in match_data
        assert "unknown_requirements" in match_data

        # 6. Skill Gaps
        print("\n6. Testing GET /skills/gaps...")
        res_gaps = await client.get(f"/skills/gaps?user_id={test_uid}&query=engineer")
        print(f"   GET /skills/gaps status: {res_gaps.status_code}")
        assert res_gaps.status_code == 200
        gaps_data = res_gaps.json()
        print(f"   Total Jobs Analyzed: {gaps_data.get('total_jobs_analyzed')}")
        print(f"   Strong Skills: {gaps_data.get('strong_skills')}")

        # 7. Save Job
        print(f"\n7. Testing POST /jobs/{real_job_id}/save...")
        save_payload = {"job_id": real_job_id, "notes": "Top priority opportunity"}
        res_save = await client.post(f"/jobs/{real_job_id}/save?user_id={test_uid}", json=save_payload)
        print(f"   POST /jobs/{real_job_id}/save status: {res_save.status_code}")
        assert res_save.status_code == 200
        print(f"   Response: {res_save.json()}")

        # 8. Get Saved Jobs
        print("\n8. Testing GET /jobs/saved/list...")
        res_saved_list = await client.get(f"/jobs/saved/list?user_id={test_uid}")
        print(f"   GET /jobs/saved/list status: {res_saved_list.status_code}")
        assert res_saved_list.status_code == 200
        saved_items = res_saved_list.json()
        print(f"   Saved Jobs Count: {len(saved_items)}")
        assert len(saved_items) == 1
        assert saved_items[0]["job"]["id"] == real_job_id

        print("\n=== ALL SMOKE TEST STEPS PASSED PERFECTLY ===")


if __name__ == "__main__":
    asyncio.run(smoke_test())
