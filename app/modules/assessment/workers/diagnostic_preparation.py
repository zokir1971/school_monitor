"""Run one worker beside the web servers. PostgreSQL row locks permit safe restarts."""
import argparse,asyncio,logging
from app.db.session import async_session_maker,engine
from app.core.config import get_settings
from app.modules.assessment.services.diagnostic_preparation_service import process_one


async def run(once=False):
    from app.core.feature_flags import assessment_enabled
    if not assessment_enabled():
        logging.getLogger(__name__).info("Assessment disabled; worker stopped without processing.")
        return
    logger=logging.getLogger(__name__)
    secret=get_settings().SECRET_KEY
    logger.info("Diagnostic preparation worker started; one class per transaction")
    try:
        while True:
            try:
                async with async_session_maker() as db:
                    worked=await process_one(db,secret);await db.commit()
                if once:return
                if not worked:await asyncio.sleep(2)
                else:await asyncio.sleep(0.05)
            except asyncio.CancelledError:raise
            except Exception as exc:
                logger.error('Preparation worker transaction failed (%s); retrying in 5s',type(exc).__name__)
                if once:raise
                await asyncio.sleep(5)
    finally:await engine.dispose()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--once',action='store_true',help='Process at most one class, then exit')
    args=parser.parse_args();logging.basicConfig(level=logging.INFO)
    try:asyncio.run(run(args.once))
    except KeyboardInterrupt:pass


if __name__=='__main__':main()
