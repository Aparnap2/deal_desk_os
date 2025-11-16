"""
SAP Business One Adapter

Integration adapter for SAP Business One accounting system.
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


class SAPAdapter(AccountingAdapter):
    """SAP Business One accounting system adapter."""

    def __init__(self, **config):
        """Initialize SAP adapter with configuration."""
        super().__init__(**config)
        self.server_url = config.get("server_url")
        self.company_db = config.get("company_db")
        self.username = config.get("username")
        self.password = config.get("password")
        self.session_id = None
        self.session_timeout = timedelta(minutes=30)
        self.session_created_at = None

    def _get_system_type(self) -> AccountingSystemType:
        """Return the SAP system type."""
        return AccountingSystemType.SAP

    async def _ensure_session(self) -> str:
        """Ensure we have a valid SAP session."""
        if (
            self.session_id
            and self.session_created_at
            and datetime.utcnow() - self.session_created_at < self.session_timeout
        ):
            return self.session_id

        # Create new session
        try:
            import httpx

            login_data = {
                "CompanyDB": self.company_db,
                "UserName": self.username,
                "Password": self.password,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/Login",
                    json=login_data,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code != 200:
                    raise AccountingError(
                        f"SAP login failed: {response.text}",
                        provider="sap"
                    )

                session_data = response.json()
                self.session_id = session_data.get("SessionId")
                self.session_created_at = datetime.utcnow()

                if not self.session_id:
                    raise AccountingError("No session ID received from SAP")

                return self.session_id

        except Exception as e:
            raise AccountingError(
                f"SAP authentication error: {str(e)}",
                provider="sap"
            )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an authenticated request to SAP API."""
        import httpx

        session_id = await self._ensure_session()
        url = f"{self.server_url}/{endpoint}"

        headers = {
            "Cookie": f"B1SESSION={session_id}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method.upper() == "PATCH":
                response = await client.patch(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                raise AccountingError(f"Unsupported HTTP method: {method}")

            if response.status_code >= 400:
                error_text = response.text
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_text = f"SAP API error: {error_data['error'].get('message', error_text)}"
                except:
                    pass

                raise AccountingError(
                    f"SAP API error ({response.status_code}): {error_text}",
                    provider="sap",
                    error_code=str(response.status_code)
                )

            return response.json()

    async def create_or_update_customer(
        self,
        customer: CustomerDetails,
        customer_id: Optional[str] = None
    ) -> CustomerResult:
        """Create or update a customer in SAP Business One."""
        try:
            customer_data = {
                "CardName": customer.name,
                "CardType": "cCustomer",
                "EmailAddress": customer.email,
                "Phone1": customer.phone,
                "Currency": customer.currency,
                "PaymentTermsCode": self._get_payment_terms_code(customer.payment_terms_days),
                "Notes": customer.notes,
                "TaxId": customer.tax_id,
                "FederalTaxID": customer.tax_id,
            }

            if customer.address:
                customer_data["Address"] = customer.address.get("line1", "")
                customer_data["Address2"] = customer.address.get("line2", "")
                customer_data["City"] = customer.address.get("city", "")
                customer_data["Country"] = customer.address.get("country", "")
                customer_data["State"] = customer.address.get("state", "")
                customer_data["ZipCode"] = customer.address.get("postal_code", "")

            if customer_id:
                # Update existing customer
                endpoint = f"BusinessPartners({customer_id})"
                result = await self._make_request("PATCH", endpoint, data=customer_data)
            else:
                # Create new customer
                endpoint = "BusinessPartners"
                result = await self._make_request("POST", endpoint, data=customer_data)

            customer_response = result
            return CustomerResult(
                success=True,
                customer_id=str(customer_response.get("CardCode", "")),
                customer_data=customer_response,
                created_at=datetime.utcnow()
            )

        except Exception as e:
            return CustomerResult(
                success=False,
                error_message=str(e),
                gateway_response={"error": str(e)}
            )

    def _get_payment_terms_code(self, days: int) -> str:
        """Map payment terms days to SAP payment terms code."""
        # This would typically be configurable based on SAP setup
        terms_mapping = {
            0: "0",  # Immediate
            7: "1",  # 7 days
            14: "2",  # 14 days
            30: "3",  # 30 days
            45: "4",  # 45 days
            60: "5",  # 60 days
            90: "6",  # 90 days
        }
        return terms_mapping.get(days, "3")  # Default to 30 days

    async def create_invoice(
        self,
        invoice_request: InvoiceRequest,
        customer_id: Optional[str] = None,
        draft: bool = True
    ) -> InvoiceResult:
        """Create an invoice in SAP Business One."""
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
                    "ItemCode": item.erp_item_id or "SVC001",  # Default service item
                    "ItemDescription": item.description,
                    "Quantity": float(item.quantity),
                    "UnitPrice": float(item.unit_price),
                    "TaxCode": item.erp_tax_code or "VAT_ST",
                }

                if item.discount_percent:
                    line_item["DiscountPercent"] = float(item.discount_percent)

                line_items.append(line_item)

            # Build invoice data
            invoice_data = {
                "CardCode": customer_id,
                "DocDate": invoice_request.invoice_date.strftime("%Y-%m-%d"),
                "DocDueDate": invoice_request.due_date.strftime("%Y-%m-%d"),
                "DocCurrency": invoice_request.currency,
                "PaymentTermsCode": self._get_payment_terms_code(invoice_request.payment_terms_days),
                "Comments": invoice_request.description,
                "DocumentLines": line_items,
                "DocStatus": "bost_Open" if not draft else "bost_Draft",
            }

            # Remove None values
            invoice_data = {k: v for k, v in invoice_data.items() if v is not None}

            endpoint = "Invoices"
            result = await self._make_request("POST", endpoint, data=invoice_data)

            invoice_response = result
            doc_entry = invoice_response.get("DocEntry")
            invoice_url = f"{self.server_url}/FormInvoices.frm?DocEntry={doc_entry}"

            return InvoiceResult(
                success=True,
                invoice_id=str(doc_entry),
                invoice_number=str(invoice_response.get("DocNum", "")),
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
        """Update an existing invoice in SAP."""
        try:
            # Format line items (similar to create_invoice)
            line_items = []
            for item in invoice_request.line_items:
                line_item = {
                    "ItemCode": item.erp_item_id or "SVC001",
                    "ItemDescription": item.description,
                    "Quantity": float(item.quantity),
                    "UnitPrice": float(item.unit_price),
                    "TaxCode": item.erp_tax_code or "VAT_ST",
                }
                line_items.append(line_item)

            invoice_data = {
                "DocDate": invoice_request.invoice_date.strftime("%Y-%m-%d"),
                "DocDueDate": invoice_request.due_date.strftime("%Y-%m-%d"),
                "DocCurrency": invoice_request.currency,
                "PaymentTermsCode": self._get_payment_terms_code(invoice_request.payment_terms_days),
                "Comments": invoice_request.description,
                "DocumentLines": line_items,
            }

            endpoint = f"Invoices({invoice_id})"
            result = await self._make_request("PATCH", endpoint, data=invoice_data)
            invoice_response = result

            return InvoiceResult(
                success=True,
                invoice_id=invoice_id,
                invoice_number=str(invoice_response.get("DocNum", "")),
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
            update_data = {"DocStatus": "bost_Open"}
            await self._make_request("PATCH", f"Invoices({invoice_id})", data=update_data)

            invoice_url = f"{self.server_url}/FormInvoices.frm?DocEntry={invoice_id}"

            if send_to_customer:
                # Send invoice via SAP email functionality
                # This would typically require additional configuration
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
            result = await self._make_request("GET", f"Invoices({invoice_id})")
            invoice = result

            # Map SAP status to our enum
            sap_status = invoice.get("DocStatus", "")
            if sap_status == "bost_Close":
                status = InvoiceStatus.PAID
            elif sap_status == "bost_Open":
                status = InvoiceStatus.POSTED
            else:
                status = InvoiceStatus.DRAFT

            return InvoiceStatusResult(
                success=True,
                invoice_id=invoice_id,
                status=status,
                amount=Decimal(str(invoice.get("DocTotal", 0))),
                paid_amount=Decimal(str(invoice.get("PaidToDate", 0))),
                currency=invoice.get("DocCurrency"),
                created_at=datetime.fromisoformat(invoice.get("CreateDate", "")) if invoice.get("CreateDate") else None,
                updated_at=datetime.fromisoformat(invoice.get("UpdateDate", "")) if invoice.get("UpdateDate") else None,
                due_date=datetime.fromisoformat(invoice.get("DocDueDate", "")).date() if invoice.get("DocDueDate") else None,
                customer_id=invoice.get("CardCode"),
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
        """Void an invoice in SAP."""
        try:
            # SAP typically creates a credit memo to void an invoice
            # This is a simplified implementation
            update_data = {
                "DocStatus": "bost_Closed",
                "Comments": f"Voided: {reason}" if reason else "Voided",
            }

            endpoint = f"Invoices({invoice_id})"
            result = await self._make_request("PATCH", endpoint, data=update_data)
            invoice_response = result

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
        """Validate connection to SAP."""
        try:
            await self._ensure_session()
            result = await self._make_request("GET", "BusinessPartners", params={"$top": 1})
            return result.get("value", []) is not None
        except Exception as e:
            logger.error(f"SAP connection validation failed: {e}")
            return False

    def get_supported_currencies(self) -> List[str]:
        """Get list of supported currencies."""
        return [
            "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "SEK", "NOK", "DKK",
            "MXN", "BRL", "ARS", "CLP", "COP", "PEN", "UYU", "CNY", "HKD",
            "SGD", "MYR", "THB", "PHP", "IDR", "VND", "KRW", "INR", "PKR",
            "BDT", "NPR", "ZAR", "NGN", "GHS", "KES", "UGX", "TZS", "MZN", "ZMW"
        ]