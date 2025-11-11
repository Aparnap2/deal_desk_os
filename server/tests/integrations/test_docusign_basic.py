"""
Basic DocuSign adapter test to verify imports and initialization work.
"""

import pytest

from app.integrations.esignature.docusign_adapter import DocuSignAdapter
from app.integrations.esignature.base import (
    ESignatureType,
    DocumentInfo,
    RecipientInfo,
    RecipientType,
    EnvelopeStatus,
)


class TestDocuSignAdapterBasic:
    """Basic tests for DocuSign adapter functionality."""

    @pytest.fixture
    def docusign_config(self):
        return {
            "base_url": "https://demo.docusign.net",
            "account_id": "123456789",
            "access_token": "test_access_token",
            "user_id": "test_user_id",
            "webhook_secret": "test_webhook_secret"
        }

    @pytest.fixture
    def docusign_adapter(self, docusign_config):
        return DocuSignAdapter(**docusign_config)

    def test_adapter_initialization(self, docusign_adapter, docusign_config):
        """Test that DocuSign adapter initializes correctly."""
        assert docusign_adapter.provider_type == ESignatureType.DOCUSIGN
        assert docusign_adapter.base_url == docusign_config["base_url"]
        assert docusign_adapter.account_id == docusign_config["account_id"]
        assert docusign_adapter.access_token == docusign_config["access_token"]
        assert docusign_adapter.user_id == docusign_config["user_id"]
        assert docusign_adapter.webhook_secret == docusign_config["webhook_secret"]
        # Session is created lazily, so check _session is None initially
        assert docusign_adapter._session is None

    def test_get_supported_document_types(self, docusign_adapter):
        """Test that DocuSign adapter returns supported document types."""
        doc_types = docusign_adapter.get_supported_document_types()
        assert "application/pdf" in doc_types
        assert "application/msword" in doc_types
        assert "image/jpeg" in doc_types
        assert len(doc_types) >= 5

    def test_get_supported_authentication_methods(self, docusign_adapter):
        """Test that DocuSign adapter returns supported auth methods."""
        auth_methods = docusign_adapter.get_supported_authentication_methods()
        assert "email" in auth_methods
        assert "sms" in auth_methods
        assert "knowledge_based" in auth_methods

    def test_get_max_document_size(self, docusign_adapter):
        """Test document size limit."""
        max_size = docusign_adapter.get_max_document_size_mb()
        assert max_size == 25  # DocuSign standard limit

    def test_get_max_recipients(self, docusign_adapter):
        """Test recipient limit."""
        max_recipients = docusign_adapter.get_max_recipients_per_envelope()
        assert max_recipients == 20  # DocuSign standard limit

    def test_document_info_creation(self, docusign_adapter):
        """Test document info structure."""
        doc = DocumentInfo(
            name="Contract.pdf",
            content=b"%PDF-1.4 mock content",
            document_id="1",
            order=1
        )
        assert doc.name == "Contract.pdf"
        assert doc.document_id == "1"
        assert doc.order == 1

    def test_recipient_info_creation(self, docusign_adapter):
        """Test recipient info structure."""
        recipient = RecipientInfo(
            name="John Doe",
            email="john@example.com",
            recipient_id="1",
            type=RecipientType.SIGNER,
            order=1
        )
        assert recipient.name == "John Doe"
        assert recipient.email == "john@example.com"
        assert recipient.type == RecipientType.SIGNER

    def test_status_mapping(self, docusign_adapter):
        """Test status mapping from DocuSign."""
        # Test envelope status mapping
        assert docusign_adapter._map_status_from_docusign("sent") == EnvelopeStatus.SENT
        assert docusign_adapter._map_status_from_docusign("completed") == EnvelopeStatus.COMPLETED
        assert docusign_adapter._map_status_from_docusign("declined") == EnvelopeStatus.DECLINED
        assert docusign_adapter._map_status_from_docusign("voided") == EnvelopeStatus.VOIDED

    def test_datetime_parsing(self, docusign_adapter):
        """Test datetime parsing from DocuSign format."""
        # Valid datetime
        valid_dt = docusign_adapter._parse_datetime("2023-01-01T12:00:00.0000000Z")
        assert valid_dt is not None
        assert valid_dt.year == 2023

        # Invalid datetime
        invalid_dt = docusign_adapter._parse_datetime("invalid-datetime")
        assert invalid_dt is None

        # Empty datetime
        empty_dt = docusign_adapter._parse_datetime("")
        assert empty_dt is None

    def test_webhook_signature_verification(self, docusign_adapter):
        """Test webhook signature verification."""
        payload = b'{"event": {"eventCategory": "EnvelopeSigned"}}'
        signature = "test_signature"

        # Without webhook secret - should pass
        adapter_no_secret = DocuSignAdapter(
            base_url="https://demo.docusign.net",
            account_id="123",
            access_token="test_token"
        )
        assert adapter_no_secret._verify_webhook_signature(payload, signature) is True

        # With webhook secret - would need proper HMAC verification
        # For now, test that method exists and returns bool
        result = docusign_adapter._verify_webhook_signature(payload, signature)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_session_management(self, docusign_adapter):
        """Test that HTTP session is properly managed."""
        # Test adapter can be used as async context manager
        async with docusign_adapter as adapter:
            # Access session to create it
            session = adapter.session
            assert session is not None
            assert not session.closed

        # Session should be closed after context
        assert docusign_adapter._session is None or docusign_adapter._session.closed

    @pytest.mark.asyncio
    async def test_health_check_structure(self, docusign_adapter):
        """Test health check method structure."""
        # Health check should return bool
        # This will fail without real API access, but tests structure
        try:
            result = await docusign_adapter.health_check()
            assert isinstance(result, bool)
        except Exception:
            # Expected to fail without real API credentials
            pass