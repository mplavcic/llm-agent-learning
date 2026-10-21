import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

CASE_FILES_PATH = Path("case_files.jsonl")
TICKETS_PATH = Path("tickets.jsonl")

CaseType = Literal["refund", "counsellor", "cancellation"]
TicketStatus = Literal["open", "triaged"]
IssueType = Literal["crash", "bug", "platform_issue"]
Severity = Literal["low", "medium", "high"]


class ArtifactError(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_evidence(evidence: list[str]) -> list[str]:
    if not isinstance(evidence, list):
        raise ArtifactError("evidence must be a list of concrete facts")
    if not evidence:
        raise ArtifactError(
            "evidence_required: evidence must contain at least one concrete fact "
            "extracted from a tool call"
        )
    cleaned = []
    for item in evidence:
        if not isinstance(item, str) or not item.strip():
            raise ArtifactError("evidence items must be non-empty strings")
        cleaned.append(item.strip())
    return cleaned


def _read_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


@dataclass(frozen=True)
class CaseFile:
    """Immutable, audit-grade case file. Recommendation != decision."""

    case_id: str
    case_type: CaseType
    created_at: str
    user_id: str
    summary: str
    evidence: list[str]
    recommendation: str


@dataclass(frozen=True)
class Ticket:
    """Immutable support ticket for engineering."""

    ticket_id: str
    created_at: str
    user_id: str
    issue_type: IssueType
    severity: Severity
    description: str
    steps_to_reproduce: list[str]
    evidence: list[str]
    status: TicketStatus


class CaseFileStore:
    """Append-only store. ID assignment lives here to avoid fan-out races."""

    def __init__(self, path: Path = CASE_FILES_PATH):
        self.path = path

    def _next_id(self) -> str:
        records = _read_lines(self.path)
        max_n = 0
        for rec in records:
            cid = rec.get("case_id", "")
            if cid.startswith("CF-"):
                try:
                    max_n = max(max_n, int(cid.split("-", 1)[1]))
                except Exception:
                    pass
        return f"CF-{max_n + 1}"

    def create(
        self,
        case_type: str,
        summary: str,
        evidence: list[str],
        recommendation: str,
        user_id: str,
    ) -> CaseFile:
        if case_type not in ("refund", "counsellor", "cancellation"):
            raise ArtifactError("invalid_case_type")
        if not isinstance(summary, str) or not summary.strip():
            raise ArtifactError("summary_required")
        if not isinstance(recommendation, str) or not recommendation.strip():
            raise ArtifactError("recommendation_required")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ArtifactError("user_id_required")
        evidence = _validate_evidence(evidence)
        case_id = self._next_id()
        record = CaseFile(
            case_id=case_id,
            case_type=case_type,
            created_at=_utc_now(),
            user_id=user_id,
            summary=summary.strip(),
            evidence=evidence,
            recommendation=recommendation.strip(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(record)) + "\n")
        return record

    def list_all(self) -> list[CaseFile]:
        out = []
        for rec in _read_lines(self.path):
            out.append(CaseFile(**rec))
        return out


class TicketStore:
    def __init__(self, path: Path = TICKETS_PATH):
        self.path = path

    def _next_id(self) -> str:
        records = _read_lines(self.path)
        max_n = 0
        for rec in records:
            tid = rec.get("ticket_id", "")
            if tid.startswith("YOC-"):
                try:
                    max_n = max(max_n, int(tid.split("-", 1)[1]))
                except Exception:
                    pass
        return f"YOC-{max_n + 1}"

    def create(
        self,
        issue_type: str,
        severity: str,
        description: str,
        steps_to_reproduce: list[str],
        evidence: list[str],
        user_id: str,
    ) -> Ticket:
        if issue_type not in ("crash", "bug", "platform_issue"):
            raise ArtifactError("invalid_issue_type")
        if severity not in ("low", "medium", "high"):
            raise ArtifactError("invalid_severity")
        if not isinstance(description, str) or not description.strip():
            raise ArtifactError("description_required")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ArtifactError("user_id_required")
        evidence = _validate_evidence(evidence)
        if not isinstance(steps_to_reproduce, list):
            raise ArtifactError("steps_to_reproduce_must_be_list")
        steps = []
        for s in steps_to_reproduce:
            if isinstance(s, str) and s.strip():
                steps.append(s.strip())
        if not steps:
            raise ArtifactError("steps_to_reproduce_required")
        ticket_id = self._next_id()
        record = Ticket(
            ticket_id=ticket_id,
            created_at=_utc_now(),
            user_id=user_id,
            issue_type=issue_type,
            severity=severity,
            description=description.strip(),
            steps_to_reproduce=steps,
            evidence=evidence,
            status="open",
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(record)) + "\n")
        return record

    def list_all(self) -> list[Ticket]:
        out = []
        for rec in _read_lines(self.path):
            out.append(Ticket(**rec))
        return out
