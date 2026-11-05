from typing import Protocol


class SMSReminderAdapter(Protocol):
    def send_if_opted_in(self, *, account_id: str, idempotency_key: str) -> None: ...


# A deployment adapter owns opt-in and phone lookup. No external sender by default.
sms_adapter: SMSReminderAdapter | None = None
