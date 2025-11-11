"""
E-signature Base Classes and Interfaces

Defines the contract and base functionality for all e-signature adapters
in the Deal Desk OS system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ESignatureType(str, Enum):
    """Supported e-signature provider types."""
    DOCUSIGN = "docusign"
    HELLOSIGN = "hellosign"
    ADOBE_SIGN = "adobe_sign"
    SIGN_NOW = "sign_now"
    SIGN_REQUEST = "sign_request"


class EnvelopeStatus(str, Enum):
    """Envelope status enumeration."""
    CREATED = "created"
    SENT = "sent"
    DELIVERED = "delivered"
    SIGNED = "signed"
    COMPLETED = "completed"
    DECLINED = "declined"
    VOIDED = "voided"
    DELETED = "deleted"
    TIMED_OUT = "timed_out"
    EXPIRED = "expired"


class RecipientStatus(str, Enum):
    """Recipient status enumeration."""
    CREATED = "created"
    SENT = "sent"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    DECLINED = "declined"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTO_RESPONDED = "auto_responded"


class RecipientType(str, Enum):
    """Recipient type enumeration."""
    SIGNER = "signer"
    CC = "cc"
    INTERMEDIARY = "intermediary"
    EDITOR = "editor"
    AGENT = "agent"
    IN_PERSON_SIGNER = "in_person_signer"
    CERTIFIED_DELIVERY = "certified_delivery"


class WebhookEventType(str, Enum):
    """Webhook event types."""
    ENVELOPE_SENT = "EnvelopeSent"
    ENVELOPE_DELIVERED = "EnvelopeDelivered"
    ENVELOPE_SIGNED = "EnvelopeSigned"
    ENVELOPE_COMPLETED = "EnvelopeCompleted"
    ENVELOPE_DECLINED = "EnvelopeDeclined"
    ENVELOPE_VOIDED = "EnvelopeVoided"
    RECIPIENT_SENT = "RecipientSent"
    RECIPIENT_COMPLETED = "RecipientCompleted"
    RECIPIENT_DECLINED = "RecipientDeclined"


@dataclass
class DocumentInfo:
    """Document information for signing."""
    name: str
    content: Optional[bytes] = None  # Raw document content
    url: Optional[str] = None  # Document URL
    document_id: Optional[str] = None
    order: int = 1
    file_type: str = "pdf"
    size_bytes: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class RecipientInfo:
    """Recipient information."""
    name: str
    email: str
    recipient_id: str
    type: RecipientType = RecipientType.SIGNER
    order: int = 1
    routing_order: Optional[int] = None
    role_name: Optional[str] = None
    tabs: Optional[Dict[str, Any]] = None  # Signature, date, text fields
    authentication: Optional[Dict[str, Any]] = None  # 2FA, ID verification
    embedded: bool = False  # Whether to use embedded signing
    redirect_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class TemplateInfo:
    """Template information."""
    template_id: str
    name: str
    description: Optional[str] = None
    documents: Optional[List[DocumentInfo]] = None
    recipients: Optional[List[RecipientInfo]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SigningUrlInfo:
    """Information for embedded signing."""
    url: str
    expires_at: Optional[datetime] = None
    user_id: Optional[str] = None
    recipient_id: Optional[str] = None
    envelope_id: Optional[str] = None


@dataclass
class RecipientResult:
    """Result of recipient operation."""
    recipient_id: str
    name: str
    email: str
    type: RecipientType
    status: RecipientStatus
    order: int
    signed_at: Optional[datetime] = None
    declined_at: Optional[datetime] = None
    decline_reason: Optional[str] = None
    signed_url: Optional[str] = None
    tabs: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class DocumentResult:
    """Result of document operation."""
    document_id: str
    name: str
    file_type: str
    size_bytes: int
    pages: int
    order: int
    content: Optional[bytes] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EnvelopeResult:
    """Result of envelope operation."""
    success: bool
    envelope_id: str
    status: EnvelopeStatus
    provider: ESignatureType
    name: Optional[str] = None
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    recipients: Optional[List[RecipientResult]] = None
    documents: Optional[List[DocumentResult]] = None
    signing_urls: Optional[List[SigningUrlInfo]] = None
    metadata: Optional[Dict[str, Any]] = None
    provider_response: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class TemplateResult:
    """Result of template operation."""
    success: bool
    template_id: str
    name: str
    provider: ESignatureType
    description: Optional[str] = None
    documents: Optional[List[DocumentResult]] = None
    recipients: Optional[List[RecipientResult]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    provider_response: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class WebhookEvent:
    """Webhook event information."""
    event_type: WebhookEventType
    provider: ESignatureType
    envelope_id: str
    timestamp: datetime
    data: Dict[str, Any]
    signature: Optional[str] = None
    recipient_id: Optional[str] = None
    document_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SignatureError(Exception):
    """E-signature provider specific errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        provider: Optional[str] = None,
        provider_response: Optional[Dict[str, Any]] = None,
        envelope_id: Optional[str] = None
    ):
        super().__init__(message)
        self.error_message = message
        self.error_code = error_code
        self.provider = provider
        self.provider_response = provider_response
        self.envelope_id = envelope_id


class ESignatureProvider(ABC):
    """Abstract base class for e-signature providers."""

    def __init__(self, **config):
        """Initialize the e-signature provider with configuration."""
        self.config = config
        self.provider_type = self._get_provider_type()

    @abstractmethod
    def _get_provider_type(self) -> ESignatureType:
        """Return the provider type identifier."""
        pass

    @abstractmethod
    async def create_envelope(
        self,
        name: str,
        message: str,
        documents: Optional[List[DocumentInfo]],
        recipients: List[RecipientInfo],
        template_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> EnvelopeResult:
        """
        Create an e-signature envelope.

        Args:
            name: Envelope name/title
            message: Message to recipients
            documents: Documents to sign (None if using template)
            recipients: List of recipients
            template_id: Template ID (None for ad-hoc)
            metadata: Additional metadata
            **kwargs: Additional parameters

        Returns:
            EnvelopeResult with envelope details

        Raises:
            SignatureError: If envelope creation fails
        """
        pass

    @abstractmethod
    async def get_envelope_status(self, envelope_id: str) -> EnvelopeResult:
        """
        Get the status of an envelope.

        Args:
            envelope_id: Envelope ID

        Returns:
            EnvelopeResult with current status

        Raises:
            SignatureError: If status query fails
        """
        pass

    @abstractmethod
    async def send_envelope(
        self,
        envelope_id: str,
        recipients: Optional[List[RecipientInfo]] = None,
        **kwargs
    ) -> EnvelopeResult:
        """
        Send or update envelope recipients.

        Args:
            envelope_id: Envelope ID
            recipients: Updated recipients (None to send existing)
            **kwargs: Additional parameters

        Returns:
            EnvelopeResult with send status

        Raises:
            SignatureError: If sending fails
        """
        pass

    @abstractmethod
    async def get_signing_url(
        self,
        envelope_id: str,
        recipient_id: str,
        return_url: Optional[str] = None,
        **kwargs
    ) -> SigningUrlInfo:
        """
        Get embedded signing URL for a recipient.

        Args:
            envelope_id: Envelope ID
            recipient_id: Recipient ID
            return_url: URL to redirect to after signing
            **kwargs: Additional parameters

        Returns:
            SigningUrlInfo with signing URL

        Raises:
            SignatureError: If URL generation fails
        """
        pass

    @abstractmethod
    async def get_documents(
        self,
        envelope_id: str,
        include_content: bool = False,
        **kwargs
    ) -> EnvelopeResult:
        """
        Get documents from an envelope.

        Args:
            envelope_id: Envelope ID
            include_content: Whether to include document content
            **kwargs: Additional parameters

        Returns:
            EnvelopeResult with document information

        Raises:
            SignatureError: If document retrieval fails
        """
        pass

    @abstractmethod
    async def create_template(
        self,
        name: str,
        description: str,
        documents: List[DocumentInfo],
        recipients: List[RecipientInfo],
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> TemplateResult:
        """
        Create a reusable template.

        Args:
            name: Template name
            description: Template description
            documents: Template documents
            recipients: Template recipients with roles
            metadata: Additional metadata
            **kwargs: Additional parameters

        Returns:
            TemplateResult with template details

        Raises:
            SignatureError: If template creation fails
        """
        pass

    @abstractmethod
    async def get_templates(self, **kwargs) -> List[TemplateResult]:
        """
        Get available templates.

        Args:
            **kwargs: Additional filter parameters

        Returns:
            List of TemplateResult objects

        Raises:
            SignatureError: If template retrieval fails
        """
        pass

    @abstractmethod
    async def cancel_envelope(
        self,
        envelope_id: str,
        **kwargs
    ) -> EnvelopeResult:
        """
        Cancel an envelope (if not completed).

        Args:
            envelope_id: Envelope ID
            **kwargs: Additional parameters

        Returns:
            EnvelopeResult with cancellation status

        Raises:
            SignatureError: If cancellation fails
        """
        pass

    @abstractmethod
    async def void_envelope(
        self,
        envelope_id: str,
        reason: str,
        **kwargs
    ) -> EnvelopeResult:
        """
        Void an envelope (even if completed).

        Args:
            envelope_id: Envelope ID
            reason: Void reason
            **kwargs: Additional parameters

        Returns:
            EnvelopeResult with void status

        Raises:
            SignatureError: If voiding fails
        """
        pass

    @abstractmethod
    async def verify_webhook(
        self,
        payload: bytes,
        signature: str,
        **kwargs
    ) -> WebhookEvent:
        """
        Verify and parse webhook payload.

        Args:
            payload: Raw webhook payload
            signature: Webhook signature
            **kwargs: Additional parameters

        Returns:
            Parsed webhook event

        Raises:
            SignatureError: If webhook verification fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the e-signature provider is healthy.

        Returns:
            True if provider is responding correctly

        Raises:
            SignatureError: If health check fails
        """
        pass

    def get_supported_document_types(self) -> List[str]:
        """
        Get list of supported document types.

        Returns:
            List of supported MIME types
        """
        # Default implementation - override in subclasses
        return [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/jpeg",
            "image/png",
            "text/plain"
        ]

    def get_supported_authentication_methods(self) -> List[str]:
        """
        Get list of supported signer authentication methods.

        Returns:
            List of supported authentication methods
        """
        # Default implementation - override in subclasses
        return [
            "email",
            "sms",
            "knowledge_based",
            "id_verification"
        ]

    def get_max_document_size_mb(self) -> int:
        """
        Get maximum document size in MB.

        Returns:
            Maximum document size in megabytes
        """
        # Default implementation - override in subclasses
        return 25

    def get_max_recipients_per_envelope(self) -> int:
        """
        Get maximum recipients per envelope.

        Returns:
            Maximum number of recipients
        """
        # Default implementation - override in subclasses
        return 20


class ESignatureFactory:
    """Factory for creating e-signature provider instances."""

    _providers: Dict[ESignatureType, type] = {}

    @classmethod
    def register_provider(
        cls,
        provider_type: ESignatureType,
        provider_class: type[ESignatureProvider]
    ):
        """Register an e-signature provider implementation."""
        cls._providers[provider_type] = provider_class

    @classmethod
    def create_provider(
        cls,
        provider_type: ESignatureType,
        **config
    ) -> ESignatureProvider:
        """Create an e-signature provider instance."""
        if provider_type not in cls._providers:
            raise ValueError(f"Unsupported provider type: {provider_type}")

        provider_class = cls._providers[provider_type]
        return provider_class(**config)

    @classmethod
    def get_supported_providers(cls) -> List[ESignatureType]:
        """Get list of registered provider types."""
        return list(cls._providers.keys())


# Register built-in providers when they are imported
def _register_builtin_providers():
    """Register built-in provider implementations."""
    try:
        from .docusign_adapter import DocuSignAdapter
        ESignatureFactory.register_provider(ESignatureType.DOCUSIGN, DocuSignAdapter)
    except ImportError:
        pass

    try:
        from .hellosign_adapter import HelloSignAdapter
        ESignatureFactory.register_provider(ESignatureType.HELLOSIGN, HelloSignAdapter)
    except ImportError:
        pass


# Register providers when module is imported
_register_builtin_providers()