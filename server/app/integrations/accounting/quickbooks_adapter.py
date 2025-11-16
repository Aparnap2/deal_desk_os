"""
QuickBooks Online Adapter

Integration adapter for QuickBooks Online accounting system.
Supports customer management, invoice creation, and payment tracking.
"""

import json
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


class QuickBooksAdapter(AccountingAdapter):
    """QuickBooks Online accounting system adapter."""

    def __init__(self, **config):
        """Initialize QuickBooks adapter with configuration."""
        super().__init__(**config)
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        self.refresh_token = config.get("refresh_token")
        self.realm_id = config.get("realm_id")
        self.environment = config.get("environment", "sandbox")  # sandbox or production
        self.minorversion = config.get("minorversion", "70")
        self.base_url = self._get_base_url()
        self._access_token = None
        self._token_expires_at = None

    def _get_system_type(self) -> AccountingSystemType:
        """Return the QuickBooks system type."""
        return AccountingSystemType.QUICKBOOKS

    def _get_base_url(self) -> str:
        """Get the base URL for QuickBooks API."""
        if self.environment == "production":
            return "https://quickbooks.api.intuit.com/v3/company"
        return f"https://sandbox-quickbooks.api.intuit.com/v3/company"

    async def _get_access_token(self) -> str:
        """Get or refresh the access token."""
        # Check if current token is still valid
        if (
            self._access_token
            and self._token_expires_at
            and datetime.utcnow() < self._token_expires_at
        ):
            return self._access_token

        # Refresh the token
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
                    headers={
                        "Authorization": f"Basic {self._get_basic_auth()}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self.refresh_token,
                    }
                )

                if response.status_code != 200:
                    raise AccountingError(
                        f"Failed to refresh QuickBooks token: {response.text}",
                        provider="quickbooks"
                    )

                token_data = response.json()
                self._access_token = token_data["access_token"]
                self.refresh_token = token_data["refresh_token"]
                self._token_expires_at = datetime.utcnow() + timedelta(
                    seconds=int(token_data["expires_in"]) - 60  # Buffer of 60 seconds
                )

                return self._access_token

        except Exception as e:
            raise AccountingError(
                f"QuickBooks authentication error: {str(e)}",
                provider="quickbooks"
            )

    def _get_basic_auth(self) -> str:
        """Get base64 encoded basic auth header."""
        import base64
        credentials = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(credentials.encode()).decode()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an authenticated request to QuickBooks API."""
        import httpx

        access_token = await self._get_access_token()
        url = f"{self.base_url}/{self.realm_id}/{endpoint}"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                response = await client.put(url, headers=headers, json=data)
            else:
                raise AccountingError(f"Unsupported HTTP method: {method}")

            if response.status_code >= 400:
                error_text = response.text
                try:
                    error_data = response.json()
                    if "Fault" in error_data:
                        fault = error_data["Fault"]
                        error_text = f"QuickBooks API error: {fault.get('Error', {}).get('Message', error_text)}"
                except:
                    pass

                raise AccountingError(
                    f"QuickBooks API error ({response.status_code}): {error_text}",
                    provider="quickbooks",
                    error_code=str(response.status_code)
                )

            return response.json()

    async def create_or_update_customer(
        self,
        customer: CustomerDetails,
        customer_id: Optional[str] = None
    ) -> CustomerResult:
        """Create or update a customer in QuickBooks."""
        try:
            customer_data = {
                "DisplayName": customer.name,
                "PrimaryEmailAddr": {"Address": customer.email} if customer.email else None,
                "PrimaryPhone": {"FreeFormNumber": customer.phone} if customer.phone else None,
                "BillAddr": self._format_address(customer.address) if customer.address else None,
                "Notes": customer.notes,
                "Taxable": customer.tax_id is not None,
                "TaxExemptionReasonId": customer.tax_id if customer.tax_id else None,
                "CurrencyRef": {"value": customer.currency},
                "Job": False,
                "BalanceWithJobs": 0,
            }

            # Remove None values
            customer_data = {k: v for k, v in customer_data.items() if v is not None}

            if customer_id:
                # Update existing customer
                customer_data["Id"] = customer_id
                customer_data["SyncToken"] = await self._get_customer_sync_token(customer_id)
                endpoint = "customer"
                result = await self._make_request("POST", endpoint, data=customer_data)
            else:
                # Create new customer
                endpoint = "customer"
                result = await self._make_request("POST", endpoint, data=customer_data)

            customer_response = result.get("Customer", {})
            return CustomerResult(
                success=True,
                customer_id=customer_response.get("Id"),
                customer_data=customer_response,
                created_at=datetime.utcnow()
            )

        except Exception as e:
            return CustomerResult(
                success=False,
                error_message=str(e),
                gateway_response={"error": str(e)}
            )

    async def _get_customer_sync_token(self, customer_id: str) -> str:
        """Get the sync token for an existing customer."""
        try:
            result = await self._make_request("GET", f"customer/{customer_id}")
            customer = result.get("Customer", {})
            return customer.get("SyncToken", "0")
        except Exception:
            return "0"

    def _format_address(self, address: Dict[str, Any]) -> Dict[str, str]:
        """Format address for QuickBooks format."""
        return {
            "Line1": address.get("line1", ""),
            "Line2": address.get("line2", ""),
            "City": address.get("city", ""),
            "Country": address.get("country", ""),
            "CountrySubDivisionCode": address.get("state", ""),
            "PostalCode": address.get("postal_code", ""),
        }

    async def create_invoice(
        self,
        invoice_request: InvoiceRequest,
        customer_id: Optional[str] = None,
        draft: bool = True
    ) -> InvoiceResult:
        """Create an invoice in QuickBooks."""
        try:
            # Create customer if not provided
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
                    "Id": f"{i + 1}",
                    "Description": item.description,
                    "Amount": float(item.line_total_with_tax),
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {
                            "value": item.erp_item_id or "1",  # Default to services
                            "name": "Services"
                        },
                        "UnitPrice": float(item.unit_price),
                        "Qty": float(item.quantity),
                    }
                }

                if item.discount_percent:
                    line_item["SalesItemLineDetail"]["DiscountAmt"] = float(
                        item.line_total * (item.discount_percent / 100)
                    )

                if item.erp_tax_code:
                    line_item["SalesItemLineDetail"]["TaxCodeRef"] = {
                        "value": item.erp_tax_code
                    }

                line_items.append(line_item)

            # Build invoice data
            invoice_data = {
                "CustomerRef": {"value": customer_id},
                "Line": line_items,
                "TxnDate": invoice_request.invoice_date.strftime("%Y-%m-%d"),
                "DueDate": invoice_request.due_date.strftime("%Y-%m-%d"),
                "CurrencyRef": {"value": invoice_request.currency},
                "SalesTermRef": {"value": str(invoice_request.payment_terms_days)},
                "PrivateNote": invoice_request.description,
            }

            # Remove None values
            invoice_data = {k: v for k, v in invoice_data.items() if v is not None}

            endpoint = "invoice"
            result = await self._make_request("POST", endpoint, data=invoice_data)

            invoice_response = result.get("Invoice", {})
            invoice_url = f"https://app.qbo.intuit.com/app/invoice?txnId={invoice_response.get('Id')}"

            return InvoiceResult(
                success=True,
                invoice_id=invoice_response.get("Id"),
                invoice_number=invoice_response.get("DocNumber"),
                invoice_url=invoice_url,
                customer_id=customer_id,
                status=InvoiceStatus.APPROVED if not draft else InvoiceStatus.DRAFT,
                created_at=datetime.fromisoformat(invoice_response["MetaData"]["CreateTime"]),
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
        """Update an existing invoice in QuickBooks."""
        try:
            # Get current invoice for sync token
            current_result = await self._make_request("GET", f"invoice/{invoice_id}")
            current_invoice = current_result.get("Invoice", {})

            # Format line items (same as create_invoice)
            line_items = []
            for i, item in enumerate(invoice_request.line_items):
                line_item = {
                    "Id": f"{i + 1}",
                    "Description": item.description,
                    "Amount": float(item.line_total_with_tax),
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": item.erp_item_id or "1"},
                        "UnitPrice": float(item.unit_price),
                        "Qty": float(item.quantity),
                    }
                }
                line_items.append(line_item)

            # Update invoice data
            invoice_data = {
                "Id": invoice_id,
                "SyncToken": current_invoice.get("SyncToken", "0"),
                "Line": line_items,
                "TxnDate": invoice_request.invoice_date.strftime("%Y-%m-%d"),
                "DueDate": invoice_request.due_date.strftime("%Y-%m-%d"),
                "CurrencyRef": {"value": invoice_request.currency},
                "SalesTermRef": {"value": str(invoice_request.payment_terms_days)},
                "PrivateNote": invoice_request.description,
            }

            result = await self._make_request("POST", "invoice", data=invoice_data)
            invoice_response = result.get("Invoice", {})

            return InvoiceResult(
                success=True,
                invoice_id=invoice_response.get("Id"),
                invoice_number=invoice_response.get("DocNumber"),
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
            # QuickBooks automatically posts invoices upon creation
            # This method mainly handles sending to customer if requested
            invoice_url = f"https://app.qbo.intuit.com/app/invoice?txnId={invoice_id}"

            if send_to_customer:
                # Send invoice via QuickBooks email
                email_data = {
                    "SendToCustomer": True,
                    "EmailToCustomer": True,
                }
                await self._make_request("POST", f"invoice/{invoice_id}/send", data=email_data)

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
            result = await self._make_request("GET", f"invoice/{invoice_id}")
            invoice = result.get("Invoice", {})

            # Map QuickBooks status to our enum
            qb_status = invoice.get("EmailStatus", "")
            if qb_status == "EmailSent":
                status = InvoiceStatus.POSTED
            elif invoice.get("Balance", 0) == 0:
                status = InvoiceStatus.PAID
            else:
                status = InvoiceStatus.POSTED

            return InvoiceStatusResult(
                success=True,
                invoice_id=invoice_id,
                status=status,
                amount=Decimal(str(invoice.get("TotalAmt", 0))),
                paid_amount=Decimal(str(invoice.get("TotalAmt", 0) - invoice.get("Balance", 0))),
                currency=invoice.get("CurrencyRef", {}).get("value"),
                created_at=datetime.fromisoformat(invoice["MetaData"]["CreateTime"]),
                updated_at=datetime.fromisoformat(invoice["MetaData"]["LastUpdatedTime"]),
                due_date=datetime.fromisoformat(invoice["DueDate"]).date() if invoice.get("DueDate") else None,
                customer_id=invoice.get("CustomerRef", {}).get("value"),
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
        """Void an invoice in QuickBooks."""
        try:
            # Get current invoice for sync token
            current_result = await self._make_request("GET", f"invoice/{invoice_id}")
            current_invoice = current_result.get("Invoice", {})

            void_data = {
                "Id": invoice_id,
                "SyncToken": current_invoice.get("SyncToken", "0"),
                "Void": True,
                "PrivateNote": f"Voided: {reason}" if reason else "Voided",
            }

            result = await self._make_request("POST", "invoice", data=void_data)
            invoice_response = result.get("Invoice", {})

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
        """Validate connection to QuickBooks."""
        try:
            result = await self._make_request("GET", "companyinfo")
            company_info = result.get("CompanyInfo", [])
            return len(company_info) > 0
        except Exception as e:
            logger.error(f"QuickBooks connection validation failed: {e}")
            return False

    def get_supported_currencies(self) -> List[str]:
        """Get list of supported currencies."""
        return [
            "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "SEK", "NOK", "DKK",
            "MXN", "BRL", "ARS", "CLP", "COP", "PEN", "UYU", "VEF", "CNY", "HKD",
            "SGD", "MYR", "THB", "PHP", "IDR", "VND", "KRW", "INR", "PKR", "LKR",
            "BDT", "NPR", "ZAR", "NGN", "GHS", "KES", "UGX", "TZS", "MZN", "ZMW",
            "BWP", "SZL", "LSL", "NAD", "AOA", "CVE", "GWP", "SCR", "MGA", "MUR",
            "KMF", "REU", "DJF", "ETB", "SOS", "ERN", "RWF", "BIF", "TZS", "MWK",
            "ZMW", "SZL", "LSL", "NAD", "AOA", "CVE", "GWP", "SCR", "MGA", "MUR",
            "KMF", "REU", "DJF", "ETB", "SOS", "ERN", "RWF", "BIF", "TZS", "MWK"
        ]