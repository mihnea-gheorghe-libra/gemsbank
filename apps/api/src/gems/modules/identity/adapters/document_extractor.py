import hashlib
from datetime import date

from gems.modules.identity.domain.kyc import ExtractedIdentity
from gems.platform.errors import ValidationError

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


def _cnp_gender_digit(birth_year: int, is_female: bool) -> int:
    if birth_year >= 2000:
        return 6 if is_female else 5
    return 2 if is_female else 1


class DemoDocumentExtractor:
    def __init__(self, allowed_types: set[str], max_bytes: int) -> None:
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

        today = date.today()
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
