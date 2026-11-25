"""Batched organization imports; one transaction and no ORM relationship graph."""

from __future__ import annotations
from sqlalchemy import bindparam, insert, select, tuple_, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.org.models import Region, District, School
from app.modules.org.utils import normalize_text

BATCH_SIZE = 500


def batches(values):
    for start in range(0, len(values), BATCH_SIZE):
        yield values[start : start + BATCH_SIZE]


async def fetch_index(db, table, columns, keys):
    found = {}
    for batch in batches(keys):
        predicate = (
            table.c[columns[0]].in_(batch)
            if len(columns) == 1
            else tuple_(*(table.c[c] for c in columns)).in_(batch)
        )
        result = await db.execute(select(table).where(predicate).with_for_update())
        for row in result.mappings():
            key = (
                row[columns[0]] if len(columns) == 1 else tuple(row[c] for c in columns)
            )
            found[key] = dict(row)
    return found


async def add_parents(db, table, records, columns, index):
    for batch in batches(records):
        result = await db.execute(insert(table).returning(*table.c), batch)
        for row in result.mappings():
            key = (
                row[columns[0]] if len(columns) == 1 else tuple(row[c] for c in columns)
            )
            index[key] = dict(row)


class OrgImportService:
    @staticmethod
    async def import_schools_from_rows(db: AsyncSession, *, rows: list[dict]) -> dict:
        clean = []
        for row in rows:
            item = {
                k: normalize_text(row.get(k))
                for k in (
                    "region_name",
                    "district_name",
                    "school_name",
                    "settlement",
                    "address",
                )
            }
            if any(
                not item[k] for k in ("region_name", "district_name", "school_name")
            ):
                raise ValueError("Файл пустой или не содержит данных")
            item["settlement"] = item["settlement"] or None
            item["address"] = item["address"] or None
            clean.append(item)
        counts = dict(
            created_regions=0,
            created_districts=0,
            created_schools=0,
            updated_schools=0,
            skipped_schools=0,
            total_rows=len(clean),
        )
        if not clean:
            return counts
        region_table, district_table, school_table = (
            Region.__table__,
            District.__table__,
            School.__table__,
        )
        try:
            if db.get_bind().dialect.name == "postgresql":
                # Serialize simultaneous bulk imports; manual edits remain subject
                # to normal row/unique-key locks, never to process-local caching.
                await db.execute(text("SELECT pg_advisory_xact_lock(300071)"))
            region_names = list(dict.fromkeys(row["region_name"] for row in clean))
            regions = await fetch_index(db, region_table, ("name",), region_names)
            missing = [dict(name=name) for name in region_names if name not in regions]
            counts["created_regions"] = len(missing)
            await add_parents(db, region_table, missing, ("name",), regions)
            district_keys = list(
                dict.fromkeys(
                    (regions[row["region_name"]]["id"], row["district_name"])
                    for row in clean
                )
            )
            districts = await fetch_index(
                db, district_table, ("region_id", "name"), district_keys
            )
            missing = [
                dict(region_id=region, name=name)
                for region, name in district_keys
                if (region, name) not in districts
            ]
            counts["created_districts"] = len(missing)
            await add_parents(
                db, district_table, missing, ("region_id", "name"), districts
            )
            school_keys = list(
                dict.fromkeys(
                    (
                        districts[
                            (regions[row["region_name"]]["id"], row["district_name"])
                        ]["id"],
                        row["school_name"],
                    )
                    for row in clean
                )
            )
            existing = await fetch_index(
                db, school_table, ("district_id", "name"), school_keys
            )
            initial = {key: dict(row) for key, row in existing.items()}
            for row in clean:
                district_id = districts[
                    (regions[row["region_name"]]["id"], row["district_name"])
                ]["id"]
                key = (district_id, row["school_name"])
                school = existing.get(key)
                if school is None:
                    existing[key] = dict(
                        id=None,
                        district_id=district_id,
                        name=row["school_name"],
                        address=row["address"],
                        settlement=row["settlement"],
                    )
                    counts["created_schools"] += 1
                elif (
                    school["address"] != row["address"]
                    or school["settlement"] != row["settlement"]
                ):
                    school["address"] = row["address"]
                    school["settlement"] = row["settlement"]
                    counts["updated_schools"] += 1
                else:
                    counts["skipped_schools"] += 1
            new = [
                {k: v for k, v in row.items() if k != "id"}
                for key, row in existing.items()
                if key not in initial
            ]
            for batch in batches(new):
                await db.execute(insert(school_table), batch)
            changed = [
                dict(
                    _org_school_id=row["id"],
                    _org_address=row["address"],
                    _org_settlement=row["settlement"],
                )
                for key, row in existing.items()
                if key in initial
                and (
                    row["address"] != initial[key]["address"]
                    or row["settlement"] != initial[key]["settlement"]
                )
            ]
            statement = (
                update(school_table)
                .where(school_table.c.id == bindparam("_org_school_id"))
                .values(
                    address=bindparam("_org_address"),
                    settlement=bindparam("_org_settlement"),
                )
            )
            for batch in batches(changed):
                await db.execute(statement, batch)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return counts
