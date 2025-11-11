"""
DocuSign E-signature Adapter

Provides integration with DocuSign e-signature platform
for the Deal Desk OS system.
"""

import base64
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import ClientTimeout

from .base import (
    ESignatureProvider,
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

logger = logging.getLogger(__name__)


class DocuSignAdapter(ESignatureProvider):
    """DocuSign e-signature adapter."""

    def __init__(
        self,
        base_url: str,
        account_id: str,
        access_token: str,
        user_id: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        **config
    ):
        """
        Initialize DocuSign adapter.

        Args:
            base_url: DocuSign base URL (demo or production)
            account_id: DocuSign account ID
            access_token: OAuth 2.0 access token
            user_id: DocuSign user ID (for embedded signing)
            webhook_secret: Webhook verification secret
            **config: Additional configuration
        """
        super().__init__(
            base_url=base_url,
            account_id=account_id,
            access_token=access_token,
            user_id=user_id,
            webhook_secret=webhook_secret,
            **config
        )
        self.base_url = base_url.rstrip('/')
        self.account_id = account_id
        self.access_token = access_token
        self.user_id = user_id
        self.webhook_secret = webhook_secret

        # API endpoints
        self.api_base = f"{self.base_url}/restapi/v2.1"
        self.envelopes_endpoint = f"{self.api_base}/accounts/{self.account_id}/envelopes"
        self.templates_endpoint = f"{self.api_base}/accounts/{self.account_id}/templates"

        # Session will be created lazily to avoid event loop issues during initialization
        self._session = None
        self._timeout = ClientTimeout(total=30, connect=10)

    def _get_provider_type(self) -> ESignatureType:
        """Return the provider type identifier."""
        return ESignatureType.DOCUSIGN

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
        return self._session

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
        Create an e-signature envelope in DocuSign.

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
        try:
            if template_id:
                envelope_payload = self._build_template_envelope_payload(
                    template_id, recipients, name, message
                )
            else:
                envelope_payload = self._build_document_envelope_payload(
                    documents, recipients, name, message, metadata
                )

            async with self.session.post(self.envelopes_endpoint, json=envelope_payload) as response:
                await self._handle_api_error(response, "create_envelope")
                response_data = await response.json()

                envelope_id = response_data["envelopeId"]
                status = self._map_status_from_docusign(response_data.get("status", "created"))
                created_at = datetime.now(timezone.utc)

                return EnvelopeResult(
                    success=True,
                    envelope_id=envelope_id,
                    status=status,
                    provider=self.provider_type,
                    name=name,
                    message=message,
                    created_at=created_at,
                    metadata=metadata or {},
                    provider_response=response_data
                )

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in create_envelope: {e}")
            raise SignatureError(
                message=f"Failed to create envelope: {str(e)}",
                error_code="api_error",
                provider="docusign"
            )
        except Exception as e:
            logger.error(f"Unexpected error in create_envelope: {e}")
            raise SignatureError(
                message=f"Unexpected error: {str(e)}",
                error_code="unexpected_error",
                provider="docusign"
            )

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
        try:
            endpoint = f"{self.envelopes_endpoint}/{envelope_id}"

            async with self.session.get(endpoint) as response:
                await self._handle_api_error(response, "get_envelope_status")
                response_data = await response.json()

                # Get recipient information
                recipients = await self._get_envelope_recipients(envelope_id)

                status = self._map_status_from_docusign(response_data.get("status", "created"))
                created_at = self._parse_datetime(response_data.get("createdDateTime"))
                sent_at = self._parse_datetime(response_data.get("sentDateTime"))
                completed_at = self._parse_datetime(response_data.get("completedDateTime"))

                return EnvelopeResult(
                    success=True,
                    envelope_id=envelope_id,
                    status=status,
                    provider=self.provider_type,
                    name=response_data.get("emailSubject"),
                    message=response_data.get("emailBlurb"),
                    created_at=created_at,
                    sent_at=sent_at,
                    completed_at=completed_at,
                    recipients=recipients,
                    provider_response=response_data
                )

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in get_envelope_status: {e}")
            raise SignatureError(
                message=f"Failed to get envelope status: {str(e)}",
                error_code="api_error",
                provider="docusign",
                envelope_id=envelope_id
            )

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
        try:
            endpoint = f"{self.envelopes_endpoint}/{envelope_id}/views/recipient"

            payload = {
                "returnUrl": return_url or "",
                "authenticationMethod": "email",
                "userName": kwargs.get("user_name", ""),
                "email": kwargs.get("email", ""),
                "recipientId": recipient_id,
                "clientUserId": kwargs.get("client_user_id", "1001"),  # Required for embedded signing
                "pingFrequency": "600",  # 10 minutes
            }

            async with self.session.post(endpoint, json=payload) as response:
                await self._handle_api_error(response, "get_signing_url")
                response_data = await response.json()

                url = response_data.get("url")
                if not url:
                    raise SignatureError(
                        message="No signing URL returned",
                        error_code="no_url_returned",
                        provider="docusign"
                    )

                return SigningUrlInfo(
                    url=url,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    user_id=self.user_id,
                    recipient_id=recipient_id,
                    envelope_id=envelope_id
                )

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in get_signing_url: {e}")
            raise SignatureError(
                message=f"Failed to get signing URL: {str(e)}",
                error_code="api_error",
                provider="docusign"
            )

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
        try:
            endpoint = f"{self.envelopes_endpoint}/{envelope_id}/documents"

            async with self.session.get(endpoint) as response:
                await self._handle_api_error(response, "get_documents")
                response_data = await response.json()

                documents = []
                for doc_data in response_data.get("envelopeDocuments", []):
                    document_result = DocumentResult(
                        document_id=doc_data["documentId"],
                        name=doc_data["name"],
                        file_type=doc_data.get("type", "pdf"),
                        size_bytes=int(doc_data.get("sizeBytes", 0)),
                        pages=int(doc_data.get("pages", 0)),
                        order=int(doc_data.get("order", 0)),
                        download_url=f"{self.envelopes_endpoint}/{envelope_id}/documents/{doc_data['documentId']}" if include_content else None
                    )

                    # Download content if requested
                    if include_content:
                        try:
                            content_endpoint = f"{self.envelopes_endpoint}/{envelope_id}/documents/{doc_data['documentId']}"
                            async with self.session.get(content_endpoint) as content_response:
                                await self._handle_api_error(content_response, "get_document_content")
                                document_result.content = await content_response.read()
                        except Exception as e:
                            logger.warning(f"Failed to download document {doc_data['documentId']}: {e}")

                    documents.append(document_result)

                return EnvelopeResult(
                    success=True,
                    envelope_id=envelope_id,
                    status=EnvelopeStatus.COMPLETED,  # Documents available means completed
                    provider=self.provider_type,
                    documents=documents,
                    provider_response=response_data
                )

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in get_documents: {e}")
            raise SignatureError(
                message=f"Failed to get documents: {str(e)}",
                error_code="api_error",
                provider="docusign",
                envelope_id=envelope_id
            )

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
        Create a reusable template in DocuSign.

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
        try:
            payload = {
                "documents": [
                    {
                        "documentId": doc.document_id or str(i + 1),
                        "name": doc.name,
                        "documentBase64": base64.b64encode(doc.content).decode('utf-8') if doc.content else None,
                        "fileExtension": doc.file_type,
                        "order": str(doc.order)
                    }
                    for i, doc in enumerate(documents)
                ],
                "emailSubject": f"Please sign {name}",
                "emailBlurb": "Template-based signing request",
                "recipients": {
                    "signers": [
                        {
                            "recipientId": recipient.recipient_id,
                            "roleName": recipient.role_name or f"Role_{recipient.recipient_id}",
                            "routingOrder": str(recipient.order),
                            "requireSignerCertificate": "false",
                            "requireSignOnPaper": "false"
                        }
                        for recipient in recipients
                        if recipient.type == RecipientType.SIGNER
                    ],
                    "carbonCopies": [
                        {
                            "recipientId": recipient.recipient_id,
                            "roleName": recipient.role_name or f"CC_Role_{recipient.recipient_id}",
                            "routingOrder": str(recipient.order)
                        }
                        for recipient in recipients
                        if recipient.type == RecipientType.CC
                    ]
                },
                "envelopeTemplate": {
                    "name": name,
                    "description": description,
                    "shared": "false",
                    "password": ""
                }
            }

            async with self.session.post(self.templates_endpoint, json=payload) as response:
                await self._handle_api_error(response, "create_template")
                response_data = await response.json()

                template_id = response_data["templateId"]
                created_at = datetime.now(timezone.utc)

                return TemplateResult(
                    success=True,
                    template_id=template_id,
                    name=name,
                    provider=self.provider_type,
                    description=description,
                    created_at=created_at,
                    metadata=metadata or {},
                    provider_response=response_data
                )

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in create_template: {e}")
            raise SignatureError(
                message=f"Failed to create template: {str(e)}",
                error_code="api_error",
                provider="docusign"
            )

    async def get_templates(self, **kwargs) -> List[TemplateResult]:
        """
        Get available templates from DocuSign.

        Args:
            **kwargs: Additional filter parameters

        Returns:
            List of TemplateResult objects

        Raises:
            SignatureError: If template retrieval fails
        """
        try:
            async with self.session.get(self.templates_endpoint) as response:
                await self._handle_api_error(response, "get_templates")
                response_data = await response.json()

                templates = []
                for template_data in response_data.get("envelopeTemplates", []):
                    template_result = TemplateResult(
                        success=True,
                        template_id=template_data["templateId"],
                        name=template_data["name"],
                        provider=self.provider_type,
                        description=template_data.get("description"),
                        created_at=self._parse_datetime(template_data.get("created")),
                        updated_at=self._parse_datetime(template_data.get("lastModified")),
                        provider_response=template_data
                    )
                    templates.append(template_result)

                return templates

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in get_templates: {e}")
            raise SignatureError(
                message=f"Failed to get templates: {str(e)}",
                error_code="api_error",
                provider="docusign"
            )

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
        try:
            if recipients:
                # Update recipients
                recipient_payload = self._build_recipients_payload(recipients)
                endpoint = f"{self.envelopes_endpoint}/{envelope_id}/recipients"

                async with self.session.put(endpoint, json=recipient_payload) as response:
                    await self._handle_api_error(response, "update_recipients")
            else:
                # Send existing envelope
                endpoint = f"{self.envelopes_endpoint}/{envelope_id}?resend_envelope=true"

                async with self.session.put(endpoint) as response:
                    await self._handle_api_error(response, "send_envelope")

            return EnvelopeResult(
                success=True,
                envelope_id=envelope_id,
                status=EnvelopeStatus.SENT,
                provider=self.provider_type,
                sent_at=datetime.now(timezone.utc)
            )

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in send_envelope: {e}")
            raise SignatureError(
                message=f"Failed to send envelope: {str(e)}",
                error_code="api_error",
                provider="docusign",
                envelope_id=envelope_id
            )

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
        try:
            payload = {
                "status": "voided",
                "voidedReason": "Cancelled by user"
            }

            endpoint = f"{self.envelopes_endpoint}/{envelope_id}"

            async with self.session.put(endpoint, json=payload) as response:
                await self._handle_api_error(response, "cancel_envelope")

                return EnvelopeResult(
                    success=True,
                    envelope_id=envelope_id,
                    status=EnvelopeStatus.VOIDED,
                    provider=self.provider_type
                )

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in cancel_envelope: {e}")
            raise SignatureError(
                message=f"Failed to cancel envelope: {str(e)}",
                error_code="api_error",
                provider="docusign",
                envelope_id=envelope_id
            )

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
        try:
            payload = {
                "status": "voided",
                "voidedReason": reason
            }

            endpoint = f"{self.envelopes_endpoint}/{envelope_id}"

            async with self.session.put(endpoint, json=payload) as response:
                await self._handle_api_error(response, "void_envelope")

                return EnvelopeResult(
                    success=True,
                    envelope_id=envelope_id,
                    status=EnvelopeStatus.VOIDED,
                    provider=self.provider_type
                )

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign API error in void_envelope: {e}")
            raise SignatureError(
                message=f"Failed to void envelope: {str(e)}",
                error_code="api_error",
                provider="docusign",
                envelope_id=envelope_id
            )

    async def verify_webhook(
        self,
        payload: bytes,
        signature: str,
        **kwargs
    ) -> WebhookEvent:
        """
        Verify and parse DocuSign webhook payload.

        Args:
            payload: Raw webhook payload
            signature: Webhook signature
            **kwargs: Additional parameters

        Returns:
            Parsed webhook event

        Raises:
            SignatureError: If webhook verification fails
        """
        try:
            # Verify HMAC signature
            if not self._verify_webhook_signature(payload, signature):
                raise SignatureError(
                    message="Invalid webhook signature",
                    error_code="webhook_signature_invalid",
                    provider="docusign"
                )

            # Parse webhook data
            webhook_data = json.loads(payload.decode('utf-8'))

            event_info = webhook_data.get("event", {})
            envelope_info = webhook_data.get("envelope", {})
            recipient_info = webhook_data.get("recipient", {})

            # Map DocuSign event types to our enum
            event_type = self._map_webhook_event_type(event_info.get("eventCategory", "Unknown"))

            return WebhookEvent(
                event_type=event_type,
                provider=self.provider_type,
                envelope_id=envelope_info.get("envelopeId", ""),
                timestamp=self._parse_datetime(event_info.get("eventDateTime")),
                data=webhook_data,
                signature=signature,
                recipient_id=recipient_info.get("recipientId"),
                metadata={"account_id": webhook_data.get("accountId")}
            )

        except json.JSONDecodeError as e:
            raise SignatureError(
                message=f"Invalid webhook JSON: {str(e)}",
                error_code="webhook_json_invalid",
                provider="docusign"
            )

    async def health_check(self) -> bool:
        """
        Check if DocuSign API is healthy.

        Returns:
            True if DocuSign is responding correctly

        Raises:
            SignatureError: If health check fails
        """
        try:
            # Try to get user information as a simple health check
            if self.user_id:
                endpoint = f"{self.api_base}/accounts/{self.account_id}/users/{self.user_id}"
            else:
                # Fallback to get account information
                endpoint = f"{self.api_base}/accounts/{self.account_id}"

            async with self.session.get(endpoint) as response:
                return response.status == 200

        except aiohttp.ClientError as e:
            logger.error(f"DocuSign health check failed: {e}")
            return False

    async def _get_envelope_recipients(self, envelope_id: str) -> List[RecipientResult]:
        """Get recipient information for an envelope."""
        try:
            endpoint = f"{self.envelopes_endpoint}/{envelope_id}/recipients"

            async with self.session.get(endpoint) as response:
                await self._handle_api_error(response, "get_envelope_recipients")
                response_data = await response.json()

                recipients = []
                for signer in response_data.get("signers", []):
                    recipient_result = RecipientResult(
                        recipient_id=signer["recipientId"],
                        name=signer["name"],
                        email=signer["email"],
                        type=RecipientType.SIGNER,
                        status=self._map_recipient_status(signer.get("status", "created")),
                        order=int(signer.get("routingOrder", 1)),
                        signed_at=self._parse_datetime(signer.get("signedDateTime")),
                        declined_at=self._parse_datetime(signer.get("declinedDateTime")),
                        decline_reason=signer.get("declinedReason"),
                        metadata={}
                    )
                    recipients.append(recipient_result)

                for cc in response_data.get("carbonCopies", []):
                    recipient_result = RecipientResult(
                        recipient_id=cc["recipientId"],
                        name=cc["name"],
                        email=cc["email"],
                        type=RecipientType.CC,
                        status=self._map_recipient_status(cc.get("status", "created")),
                        order=int(cc.get("routingOrder", 1)),
                        metadata={}
                    )
                    recipients.append(recipient_result)

                return recipients

        except aiohttp.ClientError:
            return []  # Return empty list if we can't get recipients

    def _build_document_envelope_payload(
        self,
        documents: Optional[List[DocumentInfo]],
        recipients: List[RecipientInfo],
        name: str,
        message: str,
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build envelope payload for document-based envelopes."""
        payload = {
            "documents": [],
            "recipients": self._build_recipients_payload(recipients),
            "subject": name,
            "message": message,
            "status": "sent",
            "emailSubject": name,
            "emailBlurb": message
        }

        # Add documents
        if documents:
            for i, doc in enumerate(documents):
                doc_payload = {
                    "documentId": doc.document_id or str(i + 1),
                    "name": doc.name,
                    "fileExtension": doc.file_type,
                    "order": str(doc.order)
                }

                if doc.content:
                    doc_payload["documentBase64"] = base64.b64encode(doc.content).decode('utf-8')

                payload["documents"].append(doc_payload)

        # Add custom fields for metadata
        if metadata:
            custom_fields = []
            for key, value in metadata.items():
                custom_fields.append({
                    "name": key,
                    "required": False,
                    "show": False,
                    "value": str(value)
                })

            if custom_fields:
                payload["customFields"] = {"textCustomFields": custom_fields}

        return payload

    def _build_template_envelope_payload(
        self,
        template_id: str,
        recipients: List[RecipientInfo],
        name: str,
        message: str
    ) -> Dict[str, Any]:
        """Build envelope payload for template-based envelopes."""
        template_roles = []

        for recipient in recipients:
            role = {
                "email": recipient.email,
                "name": recipient.name,
                "roleName": recipient.role_name or f"Role_{recipient.recipient_id}",
            }

            if recipient.type == RecipientType.SIGNER:
                role["clientUserId"] = recipient.metadata.get("client_user_id", "1001") if recipient.embedded else None

            if recipient.tabs:
                role["tabs"] = recipient.tabs

            template_roles.append(role)

        return {
            "templateId": template_id,
            "templateRoles": template_roles,
            "status": "sent",
            "emailSubject": name,
            "emailBlurb": message
        }

    def _build_recipients_payload(self, recipients: List[RecipientInfo]) -> Dict[str, Any]:
        """Build recipients payload for DocuSign API."""
        payload = {
            "signers": [],
            "carbonCopies": []
        }

        for recipient in recipients:
            recipient_data = {
                "recipientId": recipient.recipient_id,
                "name": recipient.name,
                "email": recipient.email,
                "routingOrder": str(recipient.order),
            }

            if recipient.tabs:
                recipient_data["tabs"] = recipient.tabs

            if recipient.authentication:
                recipient_data["authentication"] = recipient.authentication

            if recipient.type == RecipientType.SIGNER:
                payload["signers"].append(recipient_data)
            elif recipient.type == RecipientType.CC:
                payload["carbonCopies"].append(recipient_data)

        return payload

    def _verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify DocuSign webhook signature using HMAC-SHA256."""
        if not self.webhook_secret:
            return True  # Skip verification if no secret configured

        expected_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature.lower())

    def _map_status_from_docusign(self, docusign_status: str) -> EnvelopeStatus:
        """Map DocuSign status to our EnvelopeStatus enum."""
        status_mapping = {
            "created": EnvelopeStatus.CREATED,
            "sent": EnvelopeStatus.SENT,
            "delivered": EnvelopeStatus.DELIVERED,
            "signed": EnvelopeStatus.SIGNED,
            "completed": EnvelopeStatus.COMPLETED,
            "declined": EnvelopeStatus.DECLINED,
            "voided": EnvelopeStatus.VOIDED,
            "deleted": EnvelopeStatus.DELETED,
            "timed_out": EnvelopeStatus.TIMED_OUT,
            "expired": EnvelopeStatus.EXPIRED
        }
        return status_mapping.get(docusign_status.lower(), EnvelopeStatus.CREATED)

    def _map_recipient_status(self, docusign_status: str) -> RecipientStatus:
        """Map DocuSign recipient status to our RecipientStatus enum."""
        status_mapping = {
            "created": RecipientStatus.CREATED,
            "sent": RecipientStatus.SENT,
            "delivered": RecipientStatus.DELIVERED,
            "completed": RecipientStatus.COMPLETED,
            "declined": RecipientStatus.DECLINED,
            "authentication_failed": RecipientStatus.AUTHENTICATION_FAILED,
            "auto_responded": RecipientStatus.AUTO_RESPONDED
        }
        return status_mapping.get(docusign_status.lower(), RecipientStatus.CREATED)

    def _map_webhook_event_type(self, docusign_event: str) -> WebhookEventType:
        """Map DocuSign webhook event to our WebhookEventType enum."""
        event_mapping = {
            "EnvelopeSent": WebhookEventType.ENVELOPE_SENT,
            "EnvelopeDelivered": WebhookEventType.ENVELOPE_DELIVERED,
            "EnvelopeSigned": WebhookEventType.ENVELOPE_SIGNED,
            "EnvelopeCompleted": WebhookEventType.ENVELOPE_COMPLETED,
            "EnvelopeDeclined": WebhookEventType.ENVELOPE_DECLINED,
            "EnvelopeVoided": WebhookEventType.ENVELOPE_VOIDED,
            "RecipientSent": WebhookEventType.RECIPIENT_SENT,
            "RecipientCompleted": WebhookEventType.RECIPIENT_COMPLETED,
            "RecipientDeclined": WebhookEventType.RECIPIENT_DECLINED
        }
        return event_mapping.get(docusign_event, WebhookEventType.ENVELOPE_SENT)

    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse DocuSign datetime string."""
        if not datetime_str:
            return None

        try:
            # DocuSign format: 2023-01-01T12:00:00.0000000Z
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None

    async def _handle_api_error(self, response: aiohttp.ClientResponse, operation: str):
        """Handle DocuSign API response with proper error handling."""
        if response.status in [200, 201, 204]:
            return

        error_message = f"DocuSign API error in {operation}"
        error_code = "api_error"

        try:
            error_data = await response.json()
            error_message = error_data.get("message", error_message)
            error_code = error_data.get("errorCode", error_code)
        except (aiohttp.ContentTypeError, json.JSONDecodeError):
            error_message = await response.text() or error_message

        if response.status == 401:
            raise SignatureError("Authentication failed - check access token", "AUTH_ERROR", "docusign")
        elif response.status == 403:
            raise SignatureError("Insufficient permissions", "PERMISSION_ERROR", "docusign")
        elif response.status == 404:
            raise SignatureError("Resource not found", "NOT_FOUND", "docusign")
        elif response.status == 429:
            retry_after = response.headers.get('Retry-After', '60')
            raise SignatureError(f"Rate limit exceeded, retry after {retry_after}s", "RATE_LIMIT", "docusign")
        elif response.status >= 500:
            raise SignatureError("DocuSign server error", "SERVER_ERROR", "docusign")
        else:
            raise SignatureError(error_message, error_code, "docusign")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None