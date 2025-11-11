from pydantic import AnyUrl, Field

from app.models.document import DocumentStatus
from app.schemas.common import ORMModel, Timestamped


class DealDocumentBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    uri: AnyUrl
    status: DocumentStatus = DocumentStatus.DRAFT
    version: str | None = Field(default=None, max_length=64)


class DealDocumentCreate(DealDocumentBase):
    pass


class DealDocumentUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    uri: AnyUrl | None = None
    status: DocumentStatus | None = None
    version: str | None = Field(default=None, max_length=64)


class DealDocumentRead(DealDocumentBase, Timestamped):
    id: str
    deal_id: str
