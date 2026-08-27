import asyncio
import hashlib
import logging
from datetime import date, datetime, timezone

from backend.config import Settings
from backend.helpers.context import log_event
from backend.helpers.errors import DeliveryError, ValidationError
from backend.onboarding.kyc import ExtractedIdentity
from backend.onboarding.validation import mask_cnp, validate_romanian_cnp

logger = logging.getLogger(__name__)

ALLOWED_DOC_TYPES = {"ci_front", "passport"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

SYNTHETIC_NAMES = [
    "POP ANDREI-MIHAI",
    "IONESCU MARIA-ELENA",
    "DUMITRU RADU-STEFAN",
    "GEORGESCU ANA-CRISTINA",
    "MARINESCU VLAD-NICOLAE",
    "STOICA IOANA-GABRIELA",
    "PETRESCU DAN-ALEXANDRU",
    "CONSTANTIN LAURA-MIHAELA",
]

SERIES = ["XZ", "RK", "TB", "MM", "AS", "GL", "CJ", "IF"]

MINOR_IN_ONE_OF = 8


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class AzureDocIntelDocumentExtractor:
    def __init__(
        self,
        endpoint: str | None,
        key: str | None,
        allowed_types: set[str] = ALLOWED_DOC_TYPES,
        max_bytes: int = MAX_UPLOAD_BYTES,
        min_confidence: float = 0.60,
    ) -> None:
        self._allowed_types = allowed_types
        self._max_bytes = max_bytes
        self._min_confidence = min_confidence
        self._client = None
        if endpoint and key:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
            self._client = DocumentIntelligenceClient(
                endpoint=endpoint, credential=AzureKeyCredential(key)
            )

    async def extract(self, doc_type: str, content: bytes, filename: str) -> ExtractedIdentity:
        if doc_type not in self._allowed_types:
            raise ValidationError(
                "Unsupported document type.",
                details={"field": "docType", "allowed": sorted(self._allowed_types)},
            )
        if not content:
            raise ValidationError("The uploaded file is empty.", details={"field": "file"})
        if len(content) > self._max_bytes:
            raise ValidationError(
                "The file is larger than 5 MB.",
                details={"field": "file", "maxBytes": self._max_bytes},
            )

        if not self._client:
            raise ValidationError(
                "Configurarea Azure Document Intelligence lipsește. Nu putem procesa actul.",
                details={"field": "file"}
            )

        try:
            from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
            request = AnalyzeDocumentRequest(bytes_source=content)
            poller = await asyncio.to_thread(
                self._client.begin_analyze_document,
                "prebuilt-idDocument",
                body=request
            )
            result = await asyncio.to_thread(poller.result)
        except ValidationError:
            raise
        except Exception as exc:
            log_event(logger, "ocr.processing_failed", reason=str(exc))
            raise ValidationError(
                "Nu am putut procesa imaginea încărcată. Te rugăm să încarci o poză validă.",
                details={"field": "file", "lowConfidence": True},
            ) from exc

        if not result.documents:
            raise ValidationError(
                "Calitatea imaginii este prea scăzută pentru extragere. Te rugăm să reîncarci o poză clară.",
                details={"field": "file", "lowConfidence": True},
            )

        fields = result.documents[0].fields
        if not fields:
            raise ValidationError(
                "Nu s-au putut extrage datele din document. Te rugăm să reîncarci o poză clară.",
                details={"field": "file", "lowConfidence": True},
            )

        def get_field_val(name: str) -> str | None:
            field = fields.get(name)
            if not field or not field.value_string:
                return None
            return field.value_string

        def get_date_val(name: str) -> date | None:
            field = fields.get(name)
            if not field or not field.value_date:
                return None
            return field.value_date

        first_name = get_field_val("FirstName")
        last_name = get_field_val("LastName")
        doc_number = get_field_val("DocumentNumber")
        cnp = get_field_val("PersonalNumber")
        expires_on = get_date_val("DateOfExpiration")
        birth_date = get_date_val("DateOfBirth")

        # Fallback to MachineReadableZone if CNP or other fields are missing
        mrz = fields.get("MachineReadableZone")
        if mrz and mrz.value_string:
            import re
            mrz_text = mrz.value_string.replace(" ", "")
            if not cnp:
                # CNP is often in MRZ, a 13-digit number
                match = re.search(r"([1-8]\d{12})", mrz_text)
                if match:
                    cnp = match.group(1)
            
            if not doc_number:
                # MRZ usually starts with IDROUXX123456...
                match = re.search(r"IDROU([A-Z]{2})([0-9]{6})", mrz_text)
                if match:
                    doc_number = match.group(1) + match.group(2)

        if not cnp and result.content:
            import re
            cleaned_full = re.sub(r"[^0-9A-Za-z]", "", result.content)
            candidate = (
                cleaned_full.replace("O", "0")
                .replace("o", "0")
                .replace("I", "1")
                .replace("l", "1")
                .replace("B", "8")
                .replace("S", "5")
                .replace("G", "6")
            )
            for m in re.findall(r"[1-8]\d{12}", candidate):
                is_valid, _, _ = validate_romanian_cnp(m)
                if is_valid:
                    cnp = m
                    break

        full_name = None
        if first_name and last_name:
            full_name = f"{last_name} {first_name}".strip().upper()
        elif first_name:
            full_name = first_name.upper()
        elif last_name:
            full_name = last_name.upper()

        if not full_name and mrz and mrz.value_string:
            mrz_match = re.search(r"([A-Z]+)<<([A-Z<]+)", mrz.value_string.upper().replace(" ", ""))
            if mrz_match:
                sur = re.sub(r"[^A-Z\-]", "", mrz_match.group(1)).strip()
                given = [
                    re.sub(r"[^A-Z\-]", "", part)
                    for part in mrz_match.group(2).split("<")
                    if len(part) > 1
                ]
                if sur and given:
                    full_name = f"{sur} {' '.join(given)}".strip()
                    
            mrz2_match = re.search(r"\d{6}[0-9MF][MF]?(\d{6})", mrz.value_string.replace(" ", "").upper())
            if not expires_on and mrz2_match:
                exp_str = mrz2_match.group(1)
                try:
                    expires_on = date(int(exp_str[0:2]) + 2000, int(exp_str[2:4]), int(exp_str[4:6]))
                except ValueError:
                    pass

        import logging
        log = logging.getLogger(__name__)
        log.error(f"Extracted: first_name={first_name}, last_name={last_name}, doc_number={doc_number}, cnp={cnp}, expires_on={expires_on}, birth_date={birth_date}")
        
        if not cnp:
            log.error("CNP missing or low confidence")
            raise ValidationError(
                "Nu am putut detecta un CNP cu suficientă încredere. Te rugăm să încarci o poză clară.",
                details={"field": "file", "lowConfidence": True},
            )

        is_valid, bdate_iso, _ = validate_romanian_cnp(cnp)
        if not is_valid:
            log.error(f"CNP invalid: {cnp}")
            raise ValidationError(
                "CNP-ul detectat nu este valid. Te rugăm să încarci o poză mai clară.",
                details={"field": "file", "lowConfidence": True},
            )

        if not birth_date:
            birth_date = date.fromisoformat(bdate_iso)

        if not full_name:
            log.error(f"Missing full_name. First: {first_name}, Last: {last_name}")
            raise ValidationError(
                "Nu am putut extrage numele complet. Te rugăm să încarci o poză mai clară.",
                details={"field": "file", "lowConfidence": True},
            )

        if not expires_on:
            log.error("Missing expires_on")
            raise ValidationError(
                "Nu am putut citi data de expirare a actului. Te rugăm să încarci o poză mai clară.",
                details={"field": "file", "lowConfidence": True},
            )

        if not doc_number:
            doc_number = "XXXXXX"
            
        series = "XX"
        # Often doc_number contains both series and number like "RK 123456"
        import re
        m = re.match(r"^([A-Za-z]{2})\s*([0-9]{6})$", doc_number.replace(" ", ""))
        if m:
            series = m.group(1).upper()
            doc_number = m.group(2)

        return ExtractedIdentity(
            full_name=full_name,
            birth_date=birth_date,
            cnp_masked=mask_cnp(cnp),
            document_number_masked=f"{series} ••••{doc_number[-2:]}" if len(doc_number) >= 2 else doc_number,
            expires_on=expires_on,
            cnp_raw=cnp,
        )


def _cnp_gender_digit(birth_year: int, male: bool) -> int:
    if 2000 <= birth_year <= 2099:
        return 5 if male else 6
    if 1800 <= birth_year <= 1899:
        return 3 if male else 4
    return 1 if male else 2


class DemoDocumentExtractor:
    def __init__(
        self,
        allowed_types: set[str] = ALLOWED_DOC_TYPES,
        max_bytes: int = MAX_UPLOAD_BYTES,
    ) -> None:
        self._allowed_types = allowed_types
        self._max_bytes = max_bytes

    async def extract(self, doc_type: str, content: bytes, filename: str) -> ExtractedIdentity:
        if doc_type not in self._allowed_types:
            raise ValidationError(
                "Unsupported document type.",
                details={"field": "docType", "allowed": sorted(self._allowed_types)},
            )
        if not content:
            raise ValidationError("The uploaded file is empty.", details={"field": "file"})
        if len(content) > self._max_bytes:
            raise ValidationError(
                "The file is larger than 5 MB.",
                details={"field": "file", "maxBytes": self._max_bytes},
            )

        digest = hashlib.sha256(content + filename.encode("utf-8")).digest()
        name = SYNTHETIC_NAMES[digest[0] % len(SYNTHETIC_NAMES)]
        series = SERIES[digest[1] % len(SERIES)]

        today = datetime.now(timezone.utc).date()
        if digest[10] % MINOR_IN_ONE_OF == 0:
            birth_year = today.year - 17 + digest[2] % 4
        else:
            birth_year = today.year - 66 + digest[2] % 45
        birth_month = 1 + digest[3] % 12
        birth_day = 1 + digest[4] % 28
        birth_date = date(birth_year, birth_month, birth_day)

        gender_digit = _cnp_gender_digit(birth_year, bool(digest[5] % 2))
        cnp_prefix = f"{gender_digit}{str(birth_year)[2:]}{birth_month:02d}"

        expires_on = date(
            today.year + 3 + digest[6] % 5,
            1 + digest[7] % 12,
            1 + digest[8] % 28,
        )

        return ExtractedIdentity(
            full_name=name,
            birth_date=birth_date,
            cnp_masked=f"{cnp_prefix}••••••••",
            document_number_masked=f"{series} ••••{digest[9] % 100:02d}",
            expires_on=expires_on,
        )


class ResendOtpSender:
    def __init__(self, config: Settings) -> None:
        self._config = config

    async def send(self, email: str, code: str, expires_at: datetime) -> None:
        if not self._config.resend_api_key:
            log_event(logger, "otp.not_sent_no_api_key", to=email)
            return

        import resend

        resend.api_key = self._config.resend_api_key
        minutes = max(int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds() // 60), 1)
        html = (
            '<div style="font-family:Barlow,Arial,sans-serif;color:#280725">'
            '<h2 style="color:#450C3F">GEMS</h2>'
            f'<p>Codul tău de verificare este: <strong style="font-size:22px">{code}</strong></p>'
            f"<p>Expiră în {minutes} minute. Dacă nu ai cerut tu acest cod, ignoră mesajul.</p>"
            "</div>"
        )
        try:
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": self._config.otp_from_email,
                    "to": email,
                    "subject": "Codul tău GEMS",
                    "html": html,
                },
            )
        except Exception as exc:
            log_event(logger, "otp.send_failed", to=email, reason=str(exc))
            raise DeliveryError(
                "We could not send the code to that address. Check it and try again.",
                details={"field": "email"},
            ) from exc
        log_event(logger, "otp.sent", to=email)

