# app/modules/org/service.py (сценарий и логика)

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org.models import Region, District, School


class OrgImportService:
    @staticmethod
    async def import_schools_from_rows(
            db: AsyncSession,
            *,
            rows: list[dict],
    ) -> dict:

        created_regions = 0
        created_districts = 0
        created_schools = 0
        updated_schools = 0
        skipped_schools = 0

        region_cache: dict[str, Region] = {}
        district_cache: dict[tuple[int, str], District] = {}

        for row in rows:

            region_name = row["region_name"]
            district_name = row["district_name"]
            settlement = row.get("settlement")
            school_name = row["school_name"]
            address = row.get("address")

            # -------------------------
            # REGION
            # -------------------------
            region = region_cache.get(region_name)

            if region is None:
                region = await db.scalar(
                    select(Region).where(Region.name == region_name)
                )

                if region is None:
                    region = Region(name=region_name)
                    db.add(region)
                    await db.flush()
                    created_regions += 1

                region_cache[region_name] = region

            # -------------------------
            # DISTRICT
            # -------------------------
            district_key = (region.id, district_name)
            district = district_cache.get(district_key)

            if district is None:

                district = await db.scalar(
                    select(District).where(
                        District.region_id == region.id,
                        District.name == district_name,
                    )
                )

                if district is None:
                    district = District(
                        region_id=region.id,
                        name=district_name,
                    )
                    db.add(district)
                    await db.flush()
                    created_districts += 1

                district_cache[district_key] = district

            # -------------------------
            # SCHOOL
            # -------------------------
            school = await db.scalar(
                select(School).where(
                    School.district_id == district.id,
                    School.name == school_name,
                )
            )

            if school is None:

                school = School(
                    district_id=district.id,
                    name=school_name,
                    settlement=settlement,
                    address=address,
                )

                db.add(school)
                created_schools += 1

            else:

                changed = False

                if school.address != address:
                    school.address = address
                    changed = True

                if school.settlement != settlement:
                    school.settlement = settlement
                    changed = True

                if changed:
                    updated_schools += 1
                else:
                    skipped_schools += 1

        # -------------------------
        # COMMIT
        # -------------------------
        await db.commit()

        # -------------------------
        # RESULT
        # -------------------------
        return {
            "created_regions": created_regions,
            "created_districts": created_districts,
            "created_schools": created_schools,
            "updated_schools": updated_schools,
            "skipped_schools": skipped_schools,
            "total_rows": len(rows),
        }
