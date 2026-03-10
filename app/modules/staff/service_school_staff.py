# app/modules/staff/service_school_staff.py

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models_staff_school import SchoolStaffMember
from app.modules.staff.staff_repo import SchoolStaffRepo, SchoolStaffRoleRepo
from .utils.csv_tools import read_csv_bytes, get_value, get_iin, build_full_name, map_row_to_fields
from app.modules.staff.utils.staff_position_filter import is_allowed_staff, ALLOWED_POSITIONS
from ..planning.enums import ResponsibleRole

logger = logging.getLogger(__name__)


class SchoolStaffService:
    @staticmethod
    async def page_data(db, *, school_id: int):
        members = await SchoolStaffRepo.list_members(db, school_id=school_id, include_inactive=True)
        roles_map = await SchoolStaffRepo.list_staff_roles_map(db, school_id=school_id)
        return {"members": members, "roles_map": roles_map}

    @staticmethod
    async def create_member(
            db: AsyncSession,
            *,
            school_id: int,
            full_name: str,
            iin: str,
            position_text: str,
            roles: list[dict] | None = None,
    ):
        full_name = (full_name or "").strip()
        iin = (iin or "").strip()
        position_text = (position_text or "").strip()

        if not full_name:
            raise HTTPException(status_code=400, detail="ФИО обязательно")
        if not (iin.isdigit() and len(iin) == 12):
            raise HTTPException(status_code=400, detail="ИИН должен быть 12 цифр")
        if not position_text:
            raise HTTPException(status_code=400, detail="Должность обязательна")

        # ✅ строгая проверка должности (если ты убрал ручной ввод)
        if position_text.lower() not in ALLOWED_POSITIONS:
            raise HTTPException(status_code=400, detail="Недопустимая должность")

        exists = await SchoolStaffRepo.get_member_by_iin(db, school_id=school_id, iin=iin)
        if exists:
            raise HTTPException(status_code=400, detail="Сотрудник с таким ИИН уже существует")

        # ✅ передаём position_text в создание
        m = await SchoolStaffRepo.create_member(
            db,
            school_id=school_id,
            full_name=full_name,
            iin=iin,
            position_text=position_text,
        )

        # ✅ роли опциональны
        roles = roles or []
        if roles:
            await SchoolStaffRepo.set_member_roles(
                db,
                school_id=school_id,
                member_id=m.id,
                roles=roles,
            )

        return m

    @staticmethod
    async def dismiss_member(db, *, school_id: int, member_id: int):
        m = await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)
        if not m:
            raise HTTPException(404, "Сотрудник не найден")
        await SchoolStaffRepo.dismiss_member(db, school_id=school_id, member_id=member_id)

    @staticmethod
    async def import_members(db, *, school_id: int, rows: list[dict]):
        """
        rows: [{"full_name":..., "iin":..., "roles":[{"role":..., "ctx":...}, ...]}, ...]
        upsert по iin
        """
        created = updated = skipped = 0
        errors: list[str] = []

        for i, r in enumerate(rows, start=1):
            try:
                full_name = (r.get("full_name") or "").strip()
                iin = (r.get("iin") or "").strip()
                position_text = (r.get("position_text") or "").strip()
                if not full_name:
                    raise ValueError("ФИО пустое")
                if not (iin.isdigit() and len(iin) == 12):
                    raise ValueError("ИИН невалидный")

                roles = r.get("roles") or []
                roles_tuples = [(x["role"], x.get("ctx") or "") for x in roles]

                m = await SchoolStaffRepo.get_member_by_iin(db, school_id=school_id, iin=iin)
                if not m:
                    m = await SchoolStaffRepo.create_member(
                        db, school_id=school_id, full_name=full_name, iin=iin, position_text=position_text, )
                    await SchoolStaffRepo.set_member_roles(db, school_id=school_id, member_id=m.id, roles=roles_tuples)
                    created += 1
                else:
                    # обновить имя (опционально), вернуть активность
                    m.full_name = full_name
                    m.is_active = True
                    await SchoolStaffRepo.set_member_roles(db, school_id=school_id, member_id=m.id, roles=roles_tuples)
                    updated += 1
            except Exception as e:
                errors.append(f"Строка {i}: {e}")
                skipped += 1

        return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}

    EDITABLE_FIELDS = {
        # образование
        "education", "academic_degree", "position_text", "university", "graduation_date", "diploma_no",
        "diploma_specialty", "study_type", "affiliation",
        # стаж
        "ped_start_date", "total_experience_years", "ped_experience_years",
        # категория
        "qualification_category", "qualification_order_no", "qualification_order_date",
        "attestation_date", "reattestation_date",
        # курсы
        "course_passed_date", "course_due_date", "course_place", "course_certificate_no",
        # предмет и достижения
        "subject", "awards", "creative_topic"
    }

    @staticmethod
    async def get_member(db, *, school_id: int, member_id: int):
        return await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)

    @staticmethod
    async def update_member_fields(db, *, school_id: int, member_id: int, update_data: dict):
        m = await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)
        if not m:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")

        for k, v in update_data.items():
            if k in SchoolStaffService.EDITABLE_FIELDS:
                setattr(m, k, v)

        await db.flush()
        return m


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


class SchoolStaffImportService:
    @staticmethod
    async def import_csv(db: AsyncSession, *, school_id: int, raw: bytes) -> ImportReport:
        data = read_csv_bytes(raw)
        report = ImportReport()

        bad_iin_count = 0
        missing_name_count = 0
        filtered_count = 0

        logger.info(
            "STAFF IMPORT start school_id=%s rows=%s delimiter=%r",
            school_id, len(data.rows), data.delimiter
        )

        for idx, row in enumerate(data.rows, start=1):
            try:
                if idx <= 5:
                    logger.info("ROW %s raw=%r", idx, row)

                iin = get_iin(row)
                full_name = build_full_name(row)

                if idx <= 5:
                    logger.info(
                        "IMPORT DEBUG idx=%s iin=%r full_name=%r keys=%s",
                        idx, iin, full_name, list(row.keys())
                    )

                if not iin:
                    report.skipped += 1
                    bad_iin_count += 1
                    if idx <= 20:
                        logger.info(
                            "SKIP idx=%s reason=bad_iin raw_iin=%r row=%r",
                            idx,
                            get_value(row, "ИИН", contains=["иин"]),
                            row,
                        )
                    continue

                if not full_name:
                    report.skipped += 1
                    missing_name_count += 1
                    if idx <= 20:
                        logger.info("SKIP idx=%s reason=missing_full_name row=%r", idx, row)
                    continue

                fields = map_row_to_fields(row)
                position_text = fields.get("position_text")

                if idx <= 5:
                    logger.info(
                        "IMPORT DEBUG idx=%s position=%r mapped_fields=%r",
                        idx,
                        position_text,
                        {
                            "position_text": fields.get("position_text"),
                            "education": fields.get("education"),
                            "academic_degree": fields.get("academic_degree"),
                            "qualification_category": fields.get("qualification_category"),
                        }
                    )

                if not is_allowed_staff(position_text=position_text):
                    report.skipped += 1
                    filtered_count += 1
                    if idx <= 20:
                        logger.info(
                            "SKIP idx=%s reason=filtered position=%r row=%r",
                            idx,
                            position_text,
                            row,
                        )
                    continue

                existing = await SchoolStaffRepo.get_by_iin(
                    db, school_id=school_id, iin=iin
                )

                if existing:
                    existing.full_name = full_name
                    existing.is_active = True

                    for k, v in fields.items():
                        if v is not None:
                            setattr(existing, k, v)

                    report.updated += 1
                else:
                    m = SchoolStaffMember(
                        school_id=school_id,
                        full_name=full_name,
                        iin=iin,
                        is_active=True,
                        **fields,
                    )
                    SchoolStaffRepo.create(db, member=m)
                    report.created += 1

            except Exception as e:
                report.errors += 1
                logger.exception(
                    "STAFF IMPORT ERROR idx=%s row=%r error=%s",
                    idx,
                    row,
                    str(e),
                )

        logger.info(
            "STAFF IMPORT done school_id=%s created=%s updated=%s skipped=%s errors=%s bad_iin=%s missing_name=%s filtered=%s",
            school_id,
            report.created,
            report.updated,
            report.skipped,
            report.errors,
            bad_iin_count,
            missing_name_count,
            filtered_count,
        )

        return report


class SchoolStaffRoleService:
    @staticmethod
    def _validate_roles(roles: list[dict[str, str]]) -> list[dict[str, str]]:
        allowed = {r.value for r in ResponsibleRole.__members__.values()}

        cleaned: list[dict[str, str]] = []
        for r in roles:
            role_val = (r.get("role") or "").strip()
            ctx = (r.get("context") or "").strip()

            if not role_val:
                continue
            if role_val not in allowed:
                raise HTTPException(status_code=400, detail=f"Недопустимая роль: {role_val}")

            cleaned.append({"role": role_val, "context": ctx})
        return cleaned

    @staticmethod
    async def get_member_roles_for_edit(
            db: AsyncSession, *, school_id: int, member_id: int
    ) -> list[dict[str, str]]:
        # проверим, что сотрудник принадлежит школе
        m = await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)
        if not m:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")

        existing = await SchoolStaffRoleRepo.list_by_member(db, school_id=school_id, member_id=member_id)
        return [{"role": x.role.value, "context": x.role_context or ""} for x in existing]

    @staticmethod
    async def replace_member_roles(
            db: AsyncSession,
            *,
            school_id: int,
            member_id: int,
            roles: list[dict[str, str]],
    ) -> None:
        # проверим сотрудника (безопасность)
        m = await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)
        if not m:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")

        cleaned = SchoolStaffRoleService._validate_roles(roles)

        await SchoolStaffRoleRepo.delete_by_member(db, school_id=school_id, member_id=member_id)
        if cleaned:
            await SchoolStaffRoleRepo.add_many(db, school_id=school_id, member_id=member_id, roles=cleaned)

    @staticmethod
    async def list_candidates_for_role(
            db: AsyncSession, *, school_id: int, role_value: str
    ) -> list[dict[str, str]]:
        try:
            role = ResponsibleRole(role_value)
        except ValueError:
            raise HTTPException(status_code=400, detail="Недопустимая роль")

        holders = await SchoolStaffRoleRepo.list_holders_for_role(db, school_id=school_id, role=role)

        # возвращаем удобный список для селекта/JSON
        return [
            {
                "staff_member_id": h.staff_member_id,
                "full_name": h.staff_member.full_name,
                "context": h.role_context or "",
            }
            for h in holders
        ]
