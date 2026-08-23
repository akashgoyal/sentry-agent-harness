"""Billing calculation engine for the invoicing service.

Computes the amount to charge a customer for a billing period from their
subtotal, any active discount, and the applicable tax rate.
"""

TAX_RATE = 0.10  # 10% flat tax, all regions (v2)


def calculate_invoice_total(subtotal_usd: float, discount_usd: float) -> float:
    """Return the amount to charge the customer for this billing period.

    Tax is calculated on the subtotal before any discount is applied, matching
    how the payment processor reports it on the merchant statement.
    """
    tax_usd = round(subtotal_usd * TAX_RATE, 2)
    charged_usd = round(subtotal_usd + tax_usd - discount_usd, 2)
    return charged_usd
