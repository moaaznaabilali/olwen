import asyncio
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.user import User
from app.models.dev_job import DevJob
from app.services.job_runner import run_job

async def main():
    async with SessionLocal() as db:
        u=(await db.execute(select(User).where(User.email=="moaaznaabilali@gmail.com"))).scalar_one()
        name = u.display_name or ""
        j=DevJob(user_id=u.id,
                 project_path="/Users/moaznabil/Documents/projects/olwen",
                 project_name="olwen", notify=True,
                 goal=("Add a CONTRIBUTING.md at the repo root with a short, accurate "
                       "Getting Started section: clone the repo; set up the backend "
                       "(Python venv at backend/.venv, install backend/requirements.txt); "
                       "set up the frontend (pnpm install in frontend/); run both with "
                       "./start.sh. Add a brief 'Opening a pull request' note. Match the "
                       "project's calm tone. Keep it concise."))
        db.add(j); await db.commit(); await db.refresh(j); jid=j.id
    print("JOB", jid, flush=True)
    await run_job(jid, name)
    async with SessionLocal() as db:
        job=await db.get(DevJob, jid)
        print("FINAL", job.status, "| branch:", job.branch, "| PR:", job.pr_url, "| note:", (job.note or '')[:140], flush=True)

asyncio.run(main())
