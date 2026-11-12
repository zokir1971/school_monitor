"""Run separately: python -m app.modules.assessment.workers.diagnostic_scoring.
One bounded attempt per transaction. Multiple workers use SKIP LOCKED.
--once drains the current queue then exits; existing finished attempts are included.
"""
import argparse,asyncio,logging
from sqlalchemy.exc import IntegrityError,DataError
from app.db.session import async_session_maker
from app.modules.assessment.repositories import diagnostic_result_repo as repo
from app.modules.assessment.services import diagnostic_result_service as service


async def step(factory=async_session_maker):
    from app.core.feature_flags import assessment_enabled
    if not assessment_enabled():return False
    aid=None
    try:
        async with factory() as db:
            aid=await repo.next_attempt(db)
            if aid is None:
                from app.modules.assessment.services.diagnostic_analytics_service import process_one
                worked=await process_one(db)
                await db.commit()
                return worked
            await service.process(db,aid)
            await db.commit()
        return True
    except (ValueError,KeyError,TypeError,IntegrityError,DataError) as exc:
        if aid is None:raise
        logging.getLogger(__name__).error('Diagnostic result requires inspection: attempt=%s error=%s',aid,type(exc).__name__)
        if aid is not None:
            async with factory() as db:await repo.fail(db,aid);await db.commit()
        return True


async def run(once=False):
    from app.core.feature_flags import assessment_enabled
    if not assessment_enabled():
        logging.getLogger(__name__).info("Assessment disabled; worker stopped without processing.")
        return
    while True:
        try:
            worked=await step()
            if not worked:
                if once:return
                await asyncio.sleep(2)
        except Exception:
            logging.getLogger(__name__).exception('Diagnostic result transaction rolled back; retrying')
            if once:raise
            await asyncio.sleep(5)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args.once))
