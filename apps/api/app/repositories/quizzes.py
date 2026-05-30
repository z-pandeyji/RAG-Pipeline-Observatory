from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Quiz, QuizAttempt, QuizAttemptStatus, QuizGenerationJob, QuizGenerationJobStatus


class QuizRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        workspace_id: UUID,
        user_id: UUID,
        document_id: UUID,
        title: str,
        questions: list[dict],
        answer_key: dict,
    ) -> Quiz:
        quiz = Quiz(
            workspace_id=workspace_id,
            user_id=user_id,
            document_id=document_id,
            title=title,
            questions=questions,
            answer_key=answer_key,
        )
        self.session.add(quiz)
        await self.session.flush()
        return quiz

    async def get_scoped(self, quiz_id: UUID, workspace_id: UUID, user_id: UUID) -> Quiz | None:
        result = await self.session.execute(
            select(Quiz).where(
                Quiz.id == quiz_id,
                Quiz.workspace_id == workspace_id,
                Quiz.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_scoped(self, workspace_id: UUID, user_id: UUID) -> list[Quiz]:
        result = await self.session.execute(
            select(Quiz)
            .where(Quiz.workspace_id == workspace_id, Quiz.user_id == user_id)
            .order_by(Quiz.created_at.desc())
        )
        return list(result.scalars().all())

    async def recent_question_stems(
        self,
        workspace_id: UUID,
        user_id: UUID,
        document_id: UUID | None,
        limit: int = 20,
    ) -> list[str]:
        conditions = [Quiz.workspace_id == workspace_id, Quiz.user_id == user_id]
        if document_id is not None:
            conditions.append(Quiz.document_id == document_id)
        result = await self.session.execute(
            select(Quiz).where(*conditions).order_by(Quiz.created_at.desc()).limit(limit)
        )
        stems: list[str] = []
        for quiz in result.scalars().all():
            for question in quiz.questions or []:
                stem = question.get("question") if isinstance(question, dict) else None
                if isinstance(stem, str) and stem.strip():
                    stems.append(stem.strip())
        return stems[:limit]

    async def create_attempt(
        self,
        quiz: Quiz,
        submitted_answers: dict[str, str],
        score: int,
    ) -> QuizAttempt:
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            workspace_id=quiz.workspace_id,
            user_id=quiz.user_id,
            status=QuizAttemptStatus.submitted,
            submitted_answers=submitted_answers,
            score=score,
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def create_generation_job(
        self,
        workspace_id: UUID,
        user_id: UUID,
        document_id: UUID | None,
        query: str | None,
        difficulty: str,
        quiz_type: str,
        requested_question_count: int,
    ) -> QuizGenerationJob:
        job = QuizGenerationJob(
            workspace_id=workspace_id,
            user_id=user_id,
            document_id=document_id,
            query=query,
            difficulty=difficulty,
            quiz_type=quiz_type,
            requested_question_count=requested_question_count,
            status=QuizGenerationJobStatus.queued,
            selected_chunk_ids=[],
            source_pack=[],
            validation_errors=[],
            fallback_used=False,
            warnings=[],
            timings={},
        )
        self.session.add(job)
        await self.session.flush()
        if self.session is not None:
            await self.session.refresh(job)
        return job

    async def update_job(self, job: QuizGenerationJob, **values) -> QuizGenerationJob:
        status = values.pop("status", None)
        if status is not None:
            job.status = status if isinstance(status, QuizGenerationJobStatus) else QuizGenerationJobStatus(status)
            if job.status in {QuizGenerationJobStatus.succeeded, QuizGenerationJobStatus.failed}:
                job.completed_at = datetime.now(UTC)
        for key, value in values.items():
            setattr(job, key, value)
        await self.session.flush()
        if self.session is not None:
            await self.session.refresh(job)
        return job

    async def get_job_scoped(
        self,
        job_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
    ) -> QuizGenerationJob | None:
        result = await self.session.execute(
            select(QuizGenerationJob).where(
                QuizGenerationJob.id == job_id,
                QuizGenerationJob.workspace_id == workspace_id,
                QuizGenerationJob.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_jobs_scoped(
        self,
        workspace_id: UUID,
        user_id: UUID,
        limit: int = 20,
    ) -> list[QuizGenerationJob]:
        result = await self.session.execute(
            select(QuizGenerationJob)
            .where(QuizGenerationJob.workspace_id == workspace_id, QuizGenerationJob.user_id == user_id)
            .order_by(QuizGenerationJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_scoped(self, quiz: Quiz) -> None:
        chunk_ids = []
        if isinstance(quiz.answer_key, dict):
            for value in quiz.answer_key.values():
                if isinstance(value, dict):
                    for citation in value.get("citations", []):
                        chunk_id = citation.get("chunk_id") if isinstance(citation, dict) else None
                        if chunk_id:
                            chunk_ids.append(chunk_id)
        from apps.api.app.db.models import Citation

        await self.session.execute(
            delete(QuizAttempt).where(
                QuizAttempt.quiz_id == quiz.id,
                QuizAttempt.workspace_id == quiz.workspace_id,
                QuizAttempt.user_id == quiz.user_id,
            )
        )
        if chunk_ids:
            await self.session.execute(
                delete(Citation).where(
                    Citation.workspace_id == quiz.workspace_id,
                    Citation.user_id == quiz.user_id,
                    Citation.chunk_id.in_(chunk_ids),
                )
            )
        await self.session.delete(quiz)
        await self.session.flush()
