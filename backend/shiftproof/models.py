from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict, field_validator

Role = Literal['operator', 'quality', 'supervisor']
Property = Literal['packing', 'quality', 'dispatch', 'quantity', 'task', 'operating', 'fault', 'repair', 'documents']

def now():
    return datetime.now(timezone.utc).isoformat()

def uid(prefix):
    return f'{prefix}_{uuid4().hex[:16]}'

class Actor(BaseModel):
    id: str
    name: str
    role: Role

class NoteCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    batch_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    recorded_at: datetime
    clarification_ref: str | None = None
    clarification_version: int | None = Field(default=None, ge=0)
    supersedes: list[str] = Field(default_factory=list, max_length=10)
    idempotency_key: str = Field(min_length=8, max_length=100)
    shift_id: str | None = Field(default=None, max_length=80)
    clarification_context: dict | None = None
    task_id: str | None = Field(default=None, max_length=160)
    reported_by_id: str | None = Field(default=None, max_length=100)
    @field_validator('recorded_at')
    @classmethod
    def zoned(cls, v):
        if v.tzinfo is None:
            raise ValueError('recorded_at must include a timezone')
        if v > datetime.now(timezone.utc).replace(microsecond=0) + __import__('datetime').timedelta(minutes=5):
            raise ValueError('recorded_at cannot be in the future')
        return v

class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    property: Property
    value: str | int
    excerpt: str = Field(min_length=1, max_length=2000)
    modality: Literal['actual', 'planned', 'conditional'] = 'actual'
    condition: str | None = None
    negated: bool = False
    reported_at: datetime | None = None
    owner: str | None = None
    context_refs: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('reported_at')
    @classmethod
    def zoned(cls, value):
        if value and value.tzinfo is None:
            raise ValueError('Reported time needs a timezone')
        return value

class TaskCompletion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str = Field(min_length=1, max_length=160)
    outcome: Literal['done', 'not_done', 'unclear']
    excerpt: str = Field(min_length=1, max_length=2000)
    modality: Literal['actual', 'planned', 'conditional'] = 'actual'
    negated: bool = False

class Extraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claims: list[Candidate] = Field(max_length=12)
    mentioned_batch: str | None = None
    uncertainty: str | None = None
    task_completion: TaskCompletion | None = None

class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int
    scope_shift_id: str | None = None
    action: Literal['confirm', 'reject']
    reason: str = Field(min_length=3, max_length=600)
    supersedes: list[str] = Field(default_factory=list, max_length=20)

class TranscriptReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int
    scope_shift_id: str | None = None
    claims: list[Candidate] = Field(max_length=12)
    no_operational_update: bool = False
    reason: str = Field(min_length=3, max_length=600)

class AckRequest(BaseModel):
    expected_version: int
    scope_shift_id: str | None = None
    audio_id: str | None = Field(default=None, max_length=80)
    readback: str = Field(min_length=5, max_length=1000)

class RevisionRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)
    expected_version: int
    scope_shift_id: str | None = None

class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    batch_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')

class TaskUpdate(BaseModel):
    expected_version: int
    scope_shift_id: str | None = None
    action: Literal['assign', 'complete', 'reopen', 'report_complete', 'verify']
    owner: str | None = Field(default=None, max_length=100)
    owner_id: str | None = Field(default=None, max_length=80)
    note_id: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=3, max_length=600)
