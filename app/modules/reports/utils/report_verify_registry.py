# app/modules/reports/utils/report_verify_registry.py

class ReportVerifyRegistry:
    _handlers = {}

    @classmethod
    def register(cls, report_type: str, handler):
        cls._handlers[report_type] = handler

    @classmethod
    def get(cls, report_type: str):
        handler = cls._handlers.get(report_type)

        if not handler:
            raise ValueError(
                f"Неизвестный тип отчета: {report_type}"
            )

        return handler
