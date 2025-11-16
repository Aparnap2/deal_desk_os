"""
NetSuite Adapter

Integration adapter for NetSuite accounting system.
Supports customer management, invoice creation, and payment tracking.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .base import (
    AccountingAdapter,
    AccountingError,
    AccountingSystemType,
    CustomerDetails,
    CustomerResult,
    InvoiceRequest,
    InvoiceResult,
    InvoiceStatus,
    InvoiceStatusResult,
    LineItem,
    PaymentResult,
    TaxCalculation,
)

logger = logging.getLogger(__name__)


class NetSuiteAdapter(AccountingAdapter):
    """NetSuite accounting system adapter."""

    def __init__(self, **config):
        """Initialize NetSuite adapter with configuration."""
        super().__init__(**config)
        self.account_id = config.get("account_id")
        self.consumer_key = config.get("consumer_key")
        self.consumer_secret = config.get("consumer_secret")
        self.token_id = config.get("token_id")
        self.token_secret = config.get("token_secret")
        self.environment = config.get("environment", "sandbox")  # sandbox or production
        self.restlet_url = config.get("restlet_url")
        self.base_url = self._get_base_url()

    def _get_system_type(self) -> AccountingSystemType:
        """Return the NetSuite system type."""
        return AccountingSystemType.NETSUITE

    def _get_base_url(self) -> str:
        """Get the base URL for NetSuite REST API."""
        if self.environment == "production":
            return f"https://{self.account_id}.restlets.api.netsuite.com"
        return f"https://{self.account_id}.suitetalk.api.netsuite.com"

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an authenticated request to NetSuite API."""
        try:
            import httpx
            import urllib.parse

            # OAuth 1.0a authentication for NetSuite
            import oauthlib.oauth1

            client = oauthlib.oauth1.Client(
                client_key=self.consumer_key,
                client_secret=self.consumer_secret,
                resource_owner_key=self.token_id,
                resource_owner_secret=self.token_secret,
                signature_method="HMAC-SHA256",
                signature_type="auth_header"
            )

            url = f"{self.base_url}/{endpoint}"

            # Prepare request
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            if method.upper() == "GET":
                uri, headers, body = client.sign(
                    uri=url,
                    http_method="GET",
                    body=None,
                    headers=headers
                )
                response = await httpx.AsyncClient().get(uri, headers=headers, params=params)
            elif method.upper() == "POST":
                json_data = json.dumps(data) if data else None
                uri, headers, body = client.sign(
                    uri=url,
                    http_method="POST",
                    body=json_data,
                    headers=headers
                )
                response = await httpx.AsyncClient().post(uri, headers=headers, json=data)
            elif method.upper() == "PUT":
                json_data = json.dumps(data) if data else None
                uri, headers, body = client.sign(
                    uri=url,
                    http_method="PUT",
                    body=json_data,
                    headers=headers
                )
                response = await httpx.AsyncClient().put(uri, headers=headers, json=data)
            else:
                raise AccountingError(f"Unsupported HTTP method: {method}")

            if response.status_code >= 400:
                error_text = response.text
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_text = f"NetSuite API error: {error_data['error']['message']}"
                except:
                    pass

                raise AccountingError(
                    f"NetSuite API error ({response.status_code}): {error_text}",
                    provider="netsuite",
                    error_code=str(response.status_code)
                )

            return response.json()

        except Exception as e:
            raise AccountingError(
                f"NetSuite API request failed: {str(e)}",
                provider="netsuite"
            )

    async def create_or_update_customer(
        self,
        customer: CustomerDetails,
        customer_id: Optional[str] = None
    ) -> CustomerResult:
        """Create or update a customer in NetSuite."""
        try:
            customer_data = {
                "companyname": customer.name,
                "email": customer.email,
                "phone": customer.phone,
                "currency": customer.currency,
                "terms": str(customer.customer_payment_terms_days or 30),
                "isperson": False,
                "taxable": customer.tax_id is not None,
                "taxitem": customer.tax_id if customer.tax_id else None,
            }

            if customer.address:
                customer_data["addressbook"] = [{
                    "addressbookaddress": {
                        "country": customer.address.get("country"),
                        "state": customer.address.get("state"),
                        "city": customer.address.get("city"),
                        "zip": customer.address.get("postal_code"),
                        "addr1": customer.address.get("line1"),
                        "addr2": customer.address.get("line2"),
                    }
                }]

            if customer_id:
                # Update existing customer
                customer_data["internalid"] = customer_id
                endpoint = f"record/v1/customer/{customer_id}"
                result = await self._make_request("PUT", endpoint, data=customer_data)
            else:
                # Create new customer
                endpoint = "record/v1/customer"
                result = await self._make_request("POST", endpoint, data=customer_data)

            customer_response = result.get("response", {})
            return CustomerResult(
                success=True,
                customer_id=customer_response.get("internalid"),
                customer_data=customer_response,
                created_at=datetime.utcnow()
            )

        except Exception as e:
            return CustomerResult(
                success=False,
                error_message=str(e),
                gateway_response={"error": str(e)}
            )

    async def create_invoice(
        self,
        invoice_request: InvoiceRequest,
        customer_id: Optional[str] = None,
        draft: bool = True
    ) -> InvoiceResult:
        """Create an invoice in NetSuite."""
        try:
            if not customer_id:
                customer_result = await self.create_or_update_customer(invoice_request.customer)
                if not customer_result.success:
                    return InvoiceResult(
                        success=False,
                        error_message=f"Failed to create customer: {customer_result.error_message}"
                    )
                customer_id = customer_result.customer_id

            # Format line items
            line_items = []
            for i, item in enumerate(invoice_request.line_items):
                line_item = {
                    "item": item.erp_item_id or "1",  # Default to services item
                    "description": item.description,
                    "quantity": float(item.quantity),
                    "rate": float(item.unit_price),
                    "taxcode": item.erp_tax_code or "_taxable",
                }

                if item.discount_percent:
                    line_item["custcol_discount_rate"] = float(item.discount_percent)

                line_items.append(line_item)

            # Build invoice data
            invoice_data = {
                "entity": customer_id,
                "trandate": invoice_request.invoice_date.strftime("%Y-%m-%d"),
                "duedate": invoice_request.due_date.strftime("%Y-%m-%d"),
                "currency": invoice_request.currency,
                "terms": str(invoice_request.payment_terms_days),
                "memo": invoice_request.description,
                "item": line_items,
                "status": "Open" if not draft else "Draft",
            }

            # Remove None values
            invoice_data = {k: v for k, v in invoice_data.items() if v is not None}

            endpoint = "record/v1/invoice"
            result = await self._make_request("POST", endpoint, data=invoice_data)

            invoice_response = result.get("response", {})
            invoice_url = f"https://{self.account_id}.app.netsuite.com/app/accounting/transactions/custinvc.nl?id={invoice_response.get('internalid')}"

            return InvoiceResult(
                success=True,
                invoice_id=invoice_response.get("internalid"),
                invoice_number=invoice_response.get("tranid"),
                invoice_url=invoice_url,
                customer_id=customer_id,
                status=InvoiceStatus.POSTED if not draft else InvoiceStatus.DRAFT,
                created_at=datetime.utcnow(),
                invoice_data=invoice_response
            )

        except Exception as e:
            return InvoiceResult(
                success=False,
                error_message=str(e),
                gateway_response={"error": str(e)}
            )

    async def update_invoice(
        self,
        invoice_id: str,
        invoice_request: InvoiceRequest
    ) -> InvoiceResult:
        """Update an existing invoice in NetSuite."""
        try:
            # Format line items (similar to create_invoice)
            line_items = []
            for item in invoice_request.line_items:
                line_item = {
                    "item": item.erp_item_id or "1",
                    "description": item.description,
                    "quantity": float(item.quantity),
                    "rate": float(item.unit_price),
                    "taxcode": item.erp_tax_code or "_taxable",
                }
                line_items.append(line_item)

            invoice_data = {
                "trandate": invoice_request.invoice_date.strftime("%Y-%m-%d"),
                "duedate": invoice_request.due_date.strftime("%Y-%m-%d"),
                "currency": invoice_request.currency,
                "terms": str(invoice_request.payment_terms_days),
                "memo": invoice_request.description,
                "item": line_items,
            }

            endpoint = f"record/v1/invoice/{invoice_id}"
            result = await self._make_request("PUT", endpoint, data=invoice_data)
            invoice_response = result.get("response", {})

            return InvoiceResult(
                success=True,
                invoice_id=invoice_response.get("internalid"),
                invoice_number=invoice_response.get("tranid"),
                invoice_data=invoice_response
            )

        except Exception as e:
            return InvoiceResult(
                success=False,
                error_message=str(e),
                gateway_response={"error": str(e)}
            )

    async def post_invoice(
        self,
        invoice_id: str,
        send_to_customer: bool = False
    ) -> InvoiceResult:
        """Submit a draft invoice to make it official."""
        try:
            # Update invoice status to "Open" (posted)
            update_data = {"status": "Open"}
            await self._make_request("PUT", f"record/v1/invoice/{invoice_id}", data=update_data)

            invoice_url = f"https://{self.account_id}.app.netsuite.com/app/accounting/transactions/custinvc.nl?id={invoice_id}"

            if send_to_customer:
                # Send invoice via NetSuite email functionality
                # This would typically require a separate RESTlet or SuiteTalk call
                pass

            return InvoiceResult(
                success=True,
                invoice_id=invoice_id,
                invoice_url=invoice_url,
                status=InvoiceStatus.POSTED,
                posted_at=datetime.utcnow()
            )

        except Exception as e:
            return InvoiceResult(
                success=False,
                error_message=str(e),
                gateway_response={"error": str(e)}
            )

    async def get_invoice_status(self, invoice_id: str) -> InvoiceStatusResult:
        """Get the status of an invoice."""
        try:
            result = await self._make_request("GET", f"record/v1/invoice/{invoice_id}")
            invoice = result.get("response", {})

            # Map NetSuite status to our enum
            ns_status = invoice.get("status", "")
            if ns_status == "Paid In Full":
                status = InvoiceStatus.PAID
            elif ns_status in ["Open", "Approved"]:
                status = InvoiceStatus.POSTED
            else:
                status = InvoiceStatus.DRAFT

            return InvoiceStatusResult(
                success=True,
                invoice_id=invoice_id,
                status=status,
                amount=Decimal(str(invoice.get("total", 0))),
                paid_amount=Decimal(str(invoice.get("amountpaid", 0))),
                currency=invoice.get("currency"),
                created_at=datetime.fromisoformat(invoice["createddate"]) if invoice.get("createddate") else None,
                updated_at=datetime.fromisoformat(invoice["lastmodifieddate"]) if invoice.get("lastmodifieddate") else None,
                due_date=datetime.fromisoformat(invoice["duedate"]).date() if invoice.get("duedate") else None,
                customer_id=invoice.get("entity"),
            )

        except Exception as e:
            return InvoiceStatusResult(
                success=False,
                invoice_id=invoice_id,
                gateway_response={"error": str(e)}
            )

    async def void_invoice(
        self,
        invoice_id: str,
        reason: Optional[str] = None
    ) -> InvoiceResult:
        """Void an invoice in NetSuite."""
        try:
            # NetSuite typically creates a credit memo to void an invoice
            # This is a simplified implementation
            void_data = {
                "status": "Voided",
                "memo": f"Voided: {reason}" if reason else "Voided",
            }

            endpoint = f"record/v1/invoice/{invoice_id}"
            result = await self._make_request("PUT", endpoint, data=void_data)
            invoice_response = result.get("response", {})

            return InvoiceResult(
                success=True,
                invoice_id=invoice_id,
                status=InvoiceStatus.VOID,
                invoice_data=invoice_response
            )

        except Exception as e:
            return InvoiceResult(
                success=False,
                error_message=str(e),
                gateway_response={"error": str(e)}
            )

    async def validate_connection(self) -> bool:
        """Validate connection to NetSuite."""
        try:
            result = await self._make_request("GET", "record/v1/customer")
            return result.get("response", {}).get("count", 0) >= 0
        except Exception as e:
            logger.error(f"NetSuite connection validation failed: {e}")
            return False

    def get_supported_currencies(self) -> List[str]:
        """Get list of supported currencies."""
        return [
            "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "SEK", "NOK", "DKK",
            "MXN", "BRL", "ARS", "CLP", "COP", "PEN", "UYU", "VEF", "CNY", "HKD",
            "SGD", "MYR", "THB", "PHP", "IDR", "VND", "KRW", "INR", "PKR", "LKR",
            "BDT", "NPR", "ZAR", "NGN", "GHS", "KES", "UGX", "TZS", "MZN", "ZMW"
        ]