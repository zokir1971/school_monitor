"""All document correction SQL, including shared protocol references."""
from sqlalchemy import select, update, exists, or_
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem
from app.modules.planning.models_school import SchoolPlan
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reports.models_report_signature_token import ReportSignatureToken
from app.modules.reviews.models_task_review import SchoolTaskReview, SchoolMonthPlanItemReviewResult
from app.modules.users.models import User
from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import TaskDocumentStatus, TaskDocumentSource

class DocumentCorrectionRepo:
    @staticmethod
    async def tasks(db, ids, lock=False):
        i, m, p = SchoolMonthPlanItem.__table__, SchoolMonthPlan.__table__, SchoolPlan.__table__
        stmt = select(i, p.c.school_id, p.c.status.label('annual_status'), m.c.status.label('month_status')).join(m, m.c.id == i.c.month_plan_id).join(p, p.c.id == m.c.school_plan_id).where(i.c.id.in_(ids)).order_by(i.c.id)
        if lock:
            stmt = stmt.with_for_update(of=i)
        return list((await db.execute(stmt)).mappings())

    @staticmethod
    async def documents(db, month_item_id):
        d = TaskExecutionDocument.__table__
        return list((await db.execute(select(d).where(d.c.month_item_id == month_item_id, d.c.is_current.is_(True), d.c.source == TaskDocumentSource.UPLOAD, d.c.file_path.is_not(None), d.c.file_path != '').order_by(d.c.id))).mappings())

    @staticmethod
    async def target(db, document_id):
        d, r = TaskExecutionDocument.__table__, SchoolMonthPlanItemReviewResult.__table__
        doc = (await db.execute(select(d).where(d.c.id == document_id))).mappings().first()
        if doc is None:
            return None
        protocol_ids = list((await db.execute(select(r.c.task_review_id).where(r.c.protocol_document_id == document_id).distinct())).scalars())
        return doc, protocol_ids

    @staticmethod
    async def lock_target(db, document_id, protocol_ids):
        d, r, p = TaskExecutionDocument.__table__, SchoolMonthPlanItemReviewResult.__table__, SchoolTaskReview.__table__
        protocols = []
        ids = [document_id]
        task_ids = []
        if protocol_ids:
            protocols = list((await db.execute(select(p).where(p.c.id.in_(protocol_ids)).order_by(p.c.id).with_for_update())).mappings())
            links = list((await db.execute(select(r.c.protocol_document_id, r.c.month_item_id).where(r.c.task_review_id.in_(protocol_ids)))).mappings())
            ids += [l['protocol_document_id'] for l in links if l['protocol_document_id']]
            task_ids += [l['month_item_id'] for l in links]
        docs = list((await db.execute(select(d).where(d.c.id.in_(ids)).order_by(d.c.id).with_for_update())).mappings())
        task_ids += [doc['month_item_id'] for doc in docs]
        tasks = await DocumentCorrectionRepo.tasks(db, sorted(set(task_ids)), lock=True)
        return docs, protocols, tasks

    @staticmethod
    async def save(db, *, docs, protocols, stored, actor_id, note):
        d, p, i = TaskExecutionDocument.__table__, SchoolTaskReview.__table__, SchoolMonthPlanItem.__table__
        ids = [doc['id'] for doc in docs]
        # Preserve business fields and the original completion actor/date.
        common = dict(file_path=stored.object_key, original_file_name=stored.original_file_name, stored_file_name=stored.stored_file_name, mime_type=stored.content_type, file_size=stored.file_size, uploaded_by_user_id=actor_id)
        if not protocols:
            common.update(status=TaskDocumentStatus.SUBMITTED, reviewed_at=None, reviewed_by_user_id=None)
        await db.execute(update(d).where(d.c.id.in_(ids)).values(**common, review_comment=note if protocols else '[correction_pending]\n' + note))
        if protocols:
            await db.execute(update(p).where(p.c.id.in_([row['id'] for row in protocols])).values(protocol_file_path=stored.object_key, protocol_original_file_name=stored.original_file_name, protocol_stored_file_name=stored.stored_file_name, protocol_mime_type=stored.content_type, protocol_file_size=stored.file_size))
        else:
            await db.execute(update(i).where(i.c.id.in_([doc['month_item_id'] for doc in docs]), i.c.status == PlanItemStatus.REVIEWED).values(status=PlanItemStatus.DONE))
        s = ReportSignatureToken.__table__
        await db.execute(update(s).where(s.c.document_id.in_(ids)).values(is_active=False))

    @staticmethod
    async def referenced(db, key):
        d, p = TaskExecutionDocument.__table__, SchoolTaskReview.__table__
        return bool(await db.scalar(select(or_(exists(select(d.c.id).where(d.c.file_path == key)), exists(select(p.c.id).where(p.c.protocol_file_path == key))))))

    @staticmethod
    async def admin_owns_document(db, document_id, user_id):
        d, i, m, p, u = TaskExecutionDocument.__table__, SchoolMonthPlanItem.__table__, SchoolMonthPlan.__table__, SchoolPlan.__table__, User.__table__
        return bool(await db.scalar(select(exists(select(d.c.id).join(i, i.c.id == d.c.month_item_id).join(m, m.c.id == i.c.month_plan_id).join(p, p.c.id == m.c.school_plan_id).join(u, u.c.school_id == p.c.school_id).where(d.c.id == document_id, u.c.id == user_id, u.c.role == 'school_admin')))))

    @staticmethod
    def pending_expression(item_id):
        d = TaskExecutionDocument.__table__
        return exists(select(d.c.id).where(d.c.month_item_id == item_id, d.c.is_current.is_(True), d.c.status == TaskDocumentStatus.SUBMITTED, d.c.review_comment.startswith('[correction_pending]')))

    @staticmethod
    async def pending_ids(db, ids):
        i = SchoolMonthPlanItem.__table__
        return set((await db.execute(select(i.c.id).where(i.c.id.in_(ids), DocumentCorrectionRepo.pending_expression(i.c.id)))).scalars())

    @staticmethod
    async def accept_corrections(db, ids):
        d = TaskExecutionDocument.__table__
        await db.execute(update(d).where(d.c.month_item_id.in_(ids), d.c.is_current.is_(True), d.c.status == TaskDocumentStatus.SUBMITTED, d.c.review_comment.startswith('[correction_pending]')).values(status=TaskDocumentStatus.ACCEPTED))
