
import urllib.parse
import re
try:
    from hashids import Hashids
    _hashids = Hashids(salt="mobilefix_pro_sec_2026_salt", min_length=8)
except ImportError:
    _hashids = None

def encode_id(pk):
    if pk is None:
        return ""
    if _hashids:
        try:
            return _hashids.encode(int(pk))
        except (ValueError, TypeError):
            return str(pk)
    return str(pk)

def decode_id(hashid_str):
    if not hashid_str:
        return None
    if isinstance(hashid_str, int):
        return hashid_str
    if str(hashid_str).isdigit():
        return int(hashid_str)
    if _hashids:
        try:
            decoded = _hashids.decode(str(hashid_str))
            if decoded:
                return decoded[0]
        except Exception:
            pass
    if str(hashid_str).isdigit():
        return int(hashid_str)
    return None

class HashidConverter:
    regex = '[a-zA-Z0-9_-]+'

    def to_python(self, value):
        val = decode_id(value)
        if val is None:
            raise ValueError(f"Invalid hashid: {value}")
        return val

    def to_url(self, value):
        return encode_id(value)


def format_whatsapp_number(phone):
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "92" + digits[1:]
    elif not digits.startswith("92") and len(digits) == 10:
        digits = "92" + digits
    return digits


def build_whatsapp_chat_url(phone):
    digits = format_whatsapp_number(phone)
    if not digits:
        return ""
    return f"https://api.whatsapp.com/send?phone={digits}"


def build_whatsapp_url(phone, message=""):
    digits = format_whatsapp_number(phone)
    if not digits:
        return ""

    if message:
        return f"https://api.whatsapp.com/send?phone={digits}&text={urllib.parse.quote(message)}"
    return f"https://api.whatsapp.com/send?phone={digits}"


def generate_whatsapp_intake_url(job, settings):
    """
    1ST INVOICE: Sent when customer reaches the shop and hands over phone.
    Intake Slip & Approval Receipt for customer.
    """
    customer = job.customer
    device = job.device
    curr = settings.currency or "Rs."
    shop_name = settings.shop_name or "MOBILE REPAIR SHOP"
    shop_phone = settings.shop_phone or "N/A"
    shop_address = settings.shop_address or "N/A"

    intake_date = job.created_at.strftime("%d %b %Y, %I:%M %p") if hasattr(job, 'created_at') and job.created_at else "Today"

    estimate = job.estimates.order_by("-updated_at").first()
    est_labor = float(estimate.estimated_labor_cost) if estimate and estimate.estimated_labor_cost else 0.00

    exp_date = job.expected_delivery_date.strftime("%d %b %Y") if job.expected_delivery_date else "To be confirmed"

    message = (
        f"📥 *REPAIR INTAKE & APPROVAL SLIP*\n"
        f"*{shop_name.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"Dear *{customer.name}*, 👋\n"
        f"Thank you for visiting us! Your device has been logged into our repair system. Below are your intake details:\n\n"

        f"📋 *JOB INTAKE DETAILS*\n"
        f"Job #: `{job.job_number}`\n"
        f"Date: {intake_date}\n\n"

        f"📱 *DEVICE DETAILS*\n"
        f"Device Model: *{device.brand} {device.model}*\n"
        f"IMEI / Serial: `{device.imei or 'N/A'}`\n"
        f"Color / Storage: {device.color or 'N/A'} / {device.storage or 'N/A'}\n"
        f"Condition at Intake: {job.physical_condition or device.physical_condition or 'No physical damage logged'}\n"
        f"Accessories Left: {job.accessories or 'Device Only'}\n\n"

        f"🛠️ *REPORTED FAULT / COMPLAINT*\n"
        f"_{job.complaint or 'General repair & inspection'}_\n\n"

        f"💵 *ESTIMATED COST*\n"
        f"Est. Service Fee: {curr} {est_labor:,.2f}\n"
        f"Est. Completion: {exp_date}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 *CUSTOMER TERMS & APPROVAL*\n"
        f"1. Please keep this Job # `{job.job_number}` for pickup verification.\n"
        f"2. Back up your phone data prior to hardware/software repairs.\n"
        f"3. Unclaimed devices after 30 days are subject to shop storage policy.\n\n"

        f"📞 *Shop Contact:* {shop_phone}\n"
        f"📍 *Shop Location:* {shop_address}\n\n"

        f"🙏 *Thank you for choosing {shop_name}!*"
    )

    return build_whatsapp_url(customer.whatsapp or customer.phone, message)


def generate_whatsapp_diagnosis_approval_url(job, settings, request=None):
    """
    DIAGNOSIS & APPROVAL WHATSAPP:
    Opens direct clean WhatsApp chat for pasting the generated PNG diagnosis quotation image.
    """
    customer = job.customer
    return build_whatsapp_chat_url(customer.whatsapp or customer.phone)


def generate_whatsapp_final_invoice_url(invoice, settings, request=None):
    """
    2ND INVOICE: Sent when phone is successfully repaired and ready for pickup/delivered.
    Final Settlement Bill & Payment Receipt.
    """
    job = invoice.repair_job
    customer = job.customer
    device = job.device

    curr = settings.currency or "Rs."
    shop_name = settings.shop_name or "MOBILE REPAIR SHOP"
    shop_phone = settings.shop_phone or "N/A"
    shop_address = settings.shop_address or "N/A"

    pdf_link = f"http://127.0.0.1:8000/billing/invoice/{invoice.id}/pdf/"
    image_link = f"http://127.0.0.1:8000/billing/invoice/{invoice.id}/image/"

    if request:
        pdf_link = request.build_absolute_uri(f"/billing/invoice/{invoice.id}/pdf/")
        image_link = request.build_absolute_uri(f"/billing/invoice/{invoice.id}/image/")

    parts = job.parts_used.all()
    estimate = job.estimates.order_by("-updated_at").first()
    labor = float(estimate.estimated_labor_cost) if estimate else 0.00

    items = []
    for part in parts:
        total = float(part.customer_price) * part.quantity
        items.append(f"• {part.part.name} x{part.quantity} — {curr} {total:,.2f}")

    if labor > 0:
        items.append(f"• Service & Labor Charge — {curr} {labor:,.2f}")

    items_text = "\n".join(items) if items else "• Mobile Repair & Servicing"

    due_amount = float(invoice.due_amount or 0)
    if due_amount <= 0:
        payment_status = "✅ PAID IN FULL"
    elif float(invoice.paid_amount or 0) > 0:
        payment_status = "🟡 PARTIALLY PAID"
    else:
        payment_status = "🔴 PAYMENT DUE"

    invoice_date = invoice.created_at.strftime("%d %b %Y")

    message = (
        f"🧾 *FINAL REPAIR INVOICE & RECEIPT*\n"
        f"*{shop_name.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"Dear *{customer.name}*, 👋\n"
        f"Your device repair is *COMPLETED & READY FOR PICKUP*! 🎉\n\n"

        f"📄 *INVOICE DETAILS*\n"
        f"Invoice #: `{invoice.invoice_number}`\n"
        f"Job #: `{job.job_number}`\n"
        f"Date: {invoice_date}\n\n"

        f"📱 *REPAIRED DEVICE*\n"
        f"Device: *{device.brand} {device.model}*\n"
        f"IMEI / Serial: `{device.imei or 'N/A'}`\n\n"

        f"🔧 *ITEMIZED REPAIR BREAKDOWN*\n"
        f"{items_text}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *BILL SUMMARY*\n"
        f"Subtotal: {curr} {float(invoice.subtotal or 0):,.2f}\n"
        f"Discount: - {curr} {float(invoice.discount or 0):,.2f}\n"
        f"💰 *TOTAL AMOUNT: {curr} {float(invoice.total or 0):,.2f}*\n"
        f"✅ Amount Paid: {curr} {float(invoice.paid_amount or 0):,.2f}\n"
        f"🔴 *REMAINING DUE: {curr} {due_amount:,.2f}*\n\n"

        f"*Payment Status: {payment_status}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🖼️ *View Digital Bill Image:*\n"
        f"{image_link}\n\n"

        f"📄 *Download PDF Receipt:*\n"
        f"{pdf_link}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📞 *Contact:* {shop_phone}\n"
        f"📍 *Location:* {shop_address}\n\n"

        f"🙏 *Thank you for choosing {shop_name}!*\n"
        f"⭐ We appreciate your trust in us."
    )

    return build_whatsapp_url(customer.whatsapp or customer.phone, message)

# Alias for backward compatibility
generate_whatsapp_invoice_url = generate_whatsapp_final_invoice_url


def generate_whatsapp_status_url(job, settings):
    customer = job.customer
    device = job.device

    curr = settings.currency or "Rs."

    shop_name = settings.shop_name or "MOBILE REPAIR SHOP"
    shop_phone = settings.shop_phone or "N/A"
    shop_address = settings.shop_address or "N/A"

    inv = getattr(job, "invoice", None)

    if inv and hasattr(inv, "due_amount"):
        due_amount = float(inv.due_amount or 0)
        due_str = f"{curr} {due_amount:,.2f}"
    else:
        due_amount = 0
        due_str = f"{curr} 0.00"

    # ---------------------------------------------------------
    # Status Icon
    # ---------------------------------------------------------

    status_icon = "⏳"

    if job.status == "COMPLETED":
        status_icon = "✅"
    elif job.status == "DELIVERED":
        status_icon = "🎉"
    elif job.status == "CANCELLED":
        status_icon = "❌"
    elif job.status == "IN_PROGRESS":
        status_icon = "🛠️"

    # ---------------------------------------------------------
    # Status Message
    # ---------------------------------------------------------

    message = (
        f"{status_icon} *REPAIR STATUS UPDATE*\n"
        f"*{shop_name.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"Dear *{customer.name}*, 👋\n\n"

        f"Your repair job has been updated.\n"
        f"Please find the latest details below:\n\n"

        f"🔧 *JOB DETAILS*\n"
        f"Job #: `{job.job_number}`\n"
        f"Device: {device.brand} {device.model}\n"
        f"Status: *{job.get_status_display()}*\n\n"

        f"💰 *PAYMENT*\n"
        f"Due Balance: *{due_str}*\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"

        f"📞 *Shop Phone:* {shop_phone}\n"
        f"📍 *Location:* {shop_address}\n\n"

        f"Thank you for choosing *{shop_name}*. 🙏\n"
        f"We appreciate your business."
    )

    return build_whatsapp_url(
        customer.whatsapp or customer.phone,
        message
    )
