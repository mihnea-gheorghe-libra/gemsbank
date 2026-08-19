from typing import ClassVar

from gems.platform.commandbus.bus import Command


class StartOnboarding(Command):
    command_name: ClassVar[str] = "identity.onboarding.start"


class SubmitIdentityDocument(Command):
    command_name: ClassVar[str] = "identity.onboarding.submit_document"

    kyc_case_id: str
    doc_type: str
    filename: str
    content: bytes


class SetContact(Command):
    command_name: ClassVar[str] = "identity.onboarding.set_contact"

    kyc_case_id: str
    email: str
    phone: str


class ResendCode(Command):
    command_name: ClassVar[str] = "identity.onboarding.resend_code"

    kyc_case_id: str


class VerifyCode(Command):
    command_name: ClassVar[str] = "identity.onboarding.verify_code"

    kyc_case_id: str
    code: str


class CompleteOnboarding(Command):
    command_name: ClassVar[str] = "identity.onboarding.complete"

    kyc_case_id: str
    username: str
    password: str
    pin: str
    pin_confirmation: str
