# Pricing & Discounts

- Tax is calculated on the **post-discount** subtotal — discounts apply *before* tax, not after.
- All discounts are flat USD amounts unless stated otherwise.
- `charged_total = (subtotal - discount) * (1 + tax_rate)`

This is the contract billing support and finance both quote to customers who ask for a
breakdown of their invoice. Any invoice math that doesn't reduce to this formula is a bug,
not an intentional pricing change.
