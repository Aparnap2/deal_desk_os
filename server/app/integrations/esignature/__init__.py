"""
E-signature integration modules

Provides adapters for various e-signature platforms
with consistent interface and compliance features.
"""

from .base import (
    ESignatureProvider,
    ESignatureFactory,
    ESignatureType,
    EnvelopeResult,
    TemplateResult,
    SignatureError,
    DocumentInfo,
    RecipientInfo,
    TemplateInfo,
    SigningUrlInfo,
    RecipientResult,
    DocumentResult,
    WebhookEvent,
    EnvelopeStatus,
    RecipientStatus,
    RecipientType,
    WebhookEventType,
)

__all__ = [
    "ESignatureProvider",
    "ESignatureFactory",
    "ESignatureType",
    "EnvelopeResult",
    "TemplateResult",
    "SignatureError",
    "DocumentInfo",
    "RecipientInfo",
    "TemplateInfo",
    "SigningUrlInfo",
    "RecipientResult",
    "DocumentResult",
    "WebhookEvent",
    "EnvelopeStatus",
    "RecipientStatus",
    "RecipientType",
    "WebhookEventType",
]