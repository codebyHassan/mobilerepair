from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from .models import Invoice, Payment
from core.models import log_audit
from repairs.permissions import shop_admin_required

@login_required
def invoice_list(request):
    query = request.GET.get('q', '')
    invoices_qs = Invoice.objects.select_related('repair_job', 'repair_job__customer', 'repair_job__device').all().order_by('-created_at')
    
    if query:
        invoices_qs = invoices_qs.filter(
            Q(invoice_number__icontains=query) |
            Q(repair_job__job_number__icontains=query) |
            Q(repair_job__customer__name__icontains=query) |
            Q(repair_job__customer__phone__icontains=query)
        ).distinct()
        
    return render(request, 'billing/invoice_list.html', {
        'invoices': invoices_qs,
        'query': query
    })

@login_required
def invoice_detail(request, pk):
    from core.models import ShopSetting
    invoice = get_object_or_404(Invoice.objects.select_related('repair_job', 'repair_job__customer', 'repair_job__device'), pk=pk)
    settings = ShopSetting.get_settings()
    
    if request.method == 'POST':
        try:
            from decimal import Decimal
            discount = Decimal(request.POST.get('discount', '0.00'))
            if discount < 0 or discount > invoice.subtotal:
                messages.error(request, "Invalid discount amount.")
            else:
                invoice.discount = discount
                invoice.save()
                log_audit(request, 'UPDATE', 'Invoice', invoice.invoice_number, details=f"Applied discount Rs. {discount:,.2f} on Invoice {invoice.invoice_number}", object_id=invoice.id)
                messages.success(request, "Discount applied successfully.")
                return redirect('invoice_detail', pk=invoice.id)
        except (ValueError, TypeError):
            messages.error(request, "Discount must be a valid number.")
            
    parts = invoice.repair_job.parts_used.all()
    estimate = invoice.repair_job.estimates.order_by('-updated_at').first()
    labor = estimate.estimated_labor_cost if estimate else 0.00
    
    from core.utils import generate_whatsapp_invoice_url, build_whatsapp_chat_url
    whatsapp_url = generate_whatsapp_invoice_url(invoice, settings, request)
    whatsapp_chat_url = build_whatsapp_chat_url(invoice.repair_job.customer.whatsapp or invoice.repair_job.customer.phone)
    
    context = {
        'invoice': invoice,
        'parts': parts,
        'labor': labor,
        'settings': settings,
        'whatsapp_url': whatsapp_url,
        'whatsapp_chat_url': whatsapp_chat_url,
    }
    return render(request, 'billing/invoice_detail.html', context)

@login_required
def invoice_print(request, pk):
    from core.models import ShopSetting
    invoice = get_object_or_404(Invoice, pk=pk)
    settings = ShopSetting.get_settings()
    
    parts = invoice.repair_job.parts_used.all()
    estimate = invoice.repair_job.estimates.order_by('-updated_at').first()
    labor = estimate.estimated_labor_cost if estimate else 0.00
    
    context = {
        'invoice': invoice,
        'parts': parts,
        'labor': labor,
        'settings': settings,
    }
    return render(request, 'billing/invoice_print.html', context)

@login_required
@shop_admin_required
def payment_list(request):
    from core.models import ShopSetting
    from inventory.models import SupplierPayment
    from repairs.models import TechnicianCommissionRecord
    from expenses.models import Expense
    from django.urls import reverse
    
    payments = Payment.objects.select_related('invoice', 'invoice__repair_job', 'invoice__repair_job__customer', 'invoice__repair_job__device', 'received_by').all().order_by('-created_at')
    supplier_payments = SupplierPayment.objects.select_related('supplier', 'paid_by').all().order_by('-created_at')
    paid_commissions = TechnicianCommissionRecord.objects.select_related('technician', 'repair_job', 'repair_job__customer', 'repair_job__device', 'calculated_by').filter(is_paid=True).order_by('-created_at')
    expenses = Expense.objects.select_related('category').all().order_by('-date')
    
    # Date filters
    filter_type = request.GET.get('date_filter', 'all')
    active_tab = request.GET.get('tab', 'all')
    today = timezone.localtime(timezone.now()).date()
    start_date_val = None
    end_date_val = None
    
    if filter_type == 'today':
        payments = payments.filter(created_at__date=today)
        supplier_payments = supplier_payments.filter(created_at__date=today)
        paid_commissions = paid_commissions.filter(created_at__date=today)
        expenses = expenses.filter(date=today)
    elif filter_type == 'week':
        start_date = today - timedelta(days=today.weekday())
        payments = payments.filter(created_at__date__gte=start_date)
        supplier_payments = supplier_payments.filter(created_at__date__gte=start_date)
        paid_commissions = paid_commissions.filter(created_at__date__gte=start_date)
        expenses = expenses.filter(date__gte=start_date)
    elif filter_type == 'month':
        payments = payments.filter(created_at__year=today.year, created_at__month=today.month)
        supplier_payments = supplier_payments.filter(created_at__year=today.year, created_at__month=today.month)
        paid_commissions = paid_commissions.filter(created_at__year=today.year, created_at__month=today.month)
        expenses = expenses.filter(date__year=today.year, date__month=today.month)
    elif filter_type == 'custom':
        start_date_val = request.GET.get('start_date')
        end_date_val = request.GET.get('end_date')
        if start_date_val and end_date_val:
            payments = payments.filter(created_at__date__range=[start_date_val, end_date_val])
            supplier_payments = supplier_payments.filter(created_at__date__range=[start_date_val, end_date_val])
            paid_commissions = paid_commissions.filter(created_at__date__range=[start_date_val, end_date_val])
            expenses = expenses.filter(date__range=[start_date_val, end_date_val])
            
    # Calculate Inflow Sums
    cash_sum = payments.filter(payment_method='cash').aggregate(Sum('amount'))['amount__sum'] or 0.00
    bank_sum = payments.filter(payment_method='bank_transfer').aggregate(Sum('amount'))['amount__sum'] or 0.00
    card_sum = payments.filter(payment_method='card').aggregate(Sum('amount'))['amount__sum'] or 0.00
    ep_sum = payments.filter(payment_method='easypaisa').aggregate(Sum('amount'))['amount__sum'] or 0.00
    jc_sum = payments.filter(payment_method='jazzcash').aggregate(Sum('amount'))['amount__sum'] or 0.00
    other_sum = payments.filter(payment_method='other').aggregate(Sum('amount'))['amount__sum'] or 0.00
    
    total_inflow = payments.aggregate(Sum('amount'))['amount__sum'] or 0.00
    
    # Calculate Outflow Sums
    total_supplier_paid = supplier_payments.aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_commissions_paid = paid_commissions.aggregate(Sum('commission_amount'))['commission_amount__sum'] or 0.00
    total_expenses_paid = expenses.aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_outflow = float(total_supplier_paid) + float(total_commissions_paid) + float(total_expenses_paid)
    
    net_cash_flow = float(total_inflow) - float(total_outflow)
    settings = ShopSetting.get_settings()

    # Build Unified Chronological Cash Flow Stream
    stream = []
    for p in payments:
        stream.append({
            'type': 'INFLOW',
            'category': 'Customer Payment',
            'icon': 'fa-solid fa-arrow-down-left',
            'color': '#16a34a',
            'badge_style': 'background-color: #dcfce7; color: #16a34a;',
            'ref': f"PAY-{p.id:05d}",
            'title': f"{p.invoice.repair_job.customer.name}",
            'subtitle': f"Job #{p.invoice.repair_job.job_number} (Inv #{p.invoice.invoice_number})",
            'amount': float(p.amount),
            'method': p.get_payment_method_display(),
            'recorded_by': p.received_by.username if p.received_by else 'System',
            'timestamp': p.created_at,
            'notes': p.notes or '',
            'link_url': reverse('invoice_detail', kwargs={'pk': p.invoice.id}),
        })

    for sp in supplier_payments:
        stream.append({
            'type': 'OUTFLOW',
            'category': 'Supplier Udhar Payment',
            'icon': 'fa-solid fa-truck-field',
            'color': '#dc2626',
            'badge_style': 'background-color: #fee2e2; color: #dc2626;',
            'ref': f"SUP-{sp.id:05d}",
            'title': f"{sp.supplier.name}",
            'subtitle': 'Market Parts Udhar Settlement',
            'amount': float(sp.amount),
            'method': sp.get_payment_method_display(),
            'recorded_by': sp.paid_by.username if sp.paid_by else 'System',
            'timestamp': sp.created_at,
            'notes': sp.notes or '',
            'link_url': reverse('supplier_detail', kwargs={'pk': sp.supplier.id}),
        })

    for c in paid_commissions:
        stream.append({
            'type': 'OUTFLOW',
            'category': 'Tech Commission Payout',
            'icon': 'fa-solid fa-user-gear',
            'color': '#ea580c',
            'badge_style': 'background-color: #ffedd5; color: #ea580c;',
            'ref': f"COM-{c.id:05d}",
            'title': f"{c.technician.name}",
            'subtitle': f"Job #{c.repair_job.job_number} ({c.repair_job.customer.name})",
            'amount': float(c.commission_amount),
            'method': 'Commission Payout',
            'recorded_by': c.calculated_by.username if c.calculated_by else 'System',
            'timestamp': c.created_at,
            'notes': c.notes or '',
            'link_url': reverse('repair_detail', kwargs={'pk': c.repair_job.id}),
        })

    for ex in expenses:
        ex_time = ex.created_at if hasattr(ex, 'created_at') and ex.created_at else timezone.datetime.combine(ex.date, timezone.datetime.min.time())
        if timezone.is_naive(ex_time):
            ex_time = timezone.make_aware(ex_time)
        stream.append({
            'type': 'OUTFLOW',
            'category': f"Expense: {ex.category.name}",
            'icon': 'fa-solid fa-receipt',
            'color': '#b91c1c',
            'badge_style': 'background-color: #fef2f2; color: #b91c1c;',
            'ref': f"EXP-{ex.id:05d}",
            'title': ex.category.name,
            'subtitle': ex.description or 'Shop Expense',
            'amount': float(ex.amount),
            'method': ex.payment_method.capitalize(),
            'recorded_by': 'Admin',
            'timestamp': ex_time,
            'notes': ex.description or '',
            'link_url': reverse('expense_list'),
        })

    stream.sort(key=lambda x: x['timestamp'], reverse=True)
    
    context = {
        'payments': payments,
        'supplier_payments': supplier_payments,
        'paid_commissions': paid_commissions,
        'expenses': expenses,
        'stream': stream,
        'cash_sum': cash_sum,
        'bank_sum': bank_sum,
        'card_sum': card_sum,
        'ep_sum': ep_sum,
        'jc_sum': jc_sum,
        'other_sum': other_sum,
        'total_inflow': total_inflow,
        'total_supplier_paid': total_supplier_paid,
        'total_commissions_paid': total_commissions_paid,
        'total_expenses_paid': total_expenses_paid,
        'total_outflow': total_outflow,
        'net_cash_flow': net_cash_flow,
        'settings': settings,
        'filter_type': filter_type,
        'active_tab': active_tab,
        'start_date': start_date_val,
        'end_date': end_date_val,
    }
    return render(request, 'billing/payment_list.html', context)

@login_required
def payment_create(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    if request.method == 'POST':
        try:
            from decimal import Decimal
            amount = Decimal(request.POST.get('amount', '0.00'))
            payment_method = request.POST.get('payment_method', 'cash')
            notes = request.POST.get('notes', '')
            
            if amount <= 0:
                messages.error(request, "Payment amount must be greater than zero.")
            elif amount > invoice.due_amount:
                messages.error(request, f"Amount exceeds remaining balance. Max allowed: Rs. {invoice.due_amount}")
            else:
                pmt = Payment.objects.create(
                    invoice=invoice,
                    amount=amount,
                    payment_method=payment_method,
                    notes=notes,
                    received_by=request.user
                )
                log_audit(request, 'PAYMENT', 'Payment', f"Invoice #{invoice.invoice_number}", details=f"Received payment Rs. {amount:,.2f} ({pmt.get_payment_method_display()}) for Job #{invoice.repair_job.job_number}", object_id=pmt.id)
                messages.success(request, f"Payment of Rs. {amount} registered successfully.")
        except ValueError:
            messages.error(request, "Invalid payment amount entered.")
            
        redirect_job_id = request.POST.get('redirect_job_id')
        if redirect_job_id:
            return redirect('repair_detail', pk=redirect_job_id)
            
    return redirect('invoice_detail', pk=invoice_id)

@login_required
def invoice_pdf(request, pk):
    from io import BytesIO
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from core.models import ShopSetting

    invoice = get_object_or_404(Invoice.objects.select_related('repair_job', 'repair_job__customer', 'repair_job__device'), pk=pk)
    settings = ShopSetting.get_settings()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()

    subtitle_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155'),
    )

    header_data = [
        [
            Paragraph(f"<font size=14 color='#0f172a'><b>{settings.shop_name}</b></font><br/>{settings.shop_address or ''}<br/>Phone: {settings.shop_phone or 'N/A'}", subtitle_style),
            Paragraph(f"<font size=14 color='#2563eb'><b>INVOICE RECEIPT</b></font><br/>Invoice #: <b>{invoice.invoice_number}</b><br/>Date: {invoice.created_at.strftime('%b %d, %Y')}", ParagraphStyle('RHeader', parent=subtitle_style, alignment=2))
        ]
    ]
    header_table = Table(header_data, colWidths=[270, 270])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(header_table)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=14))

    job = invoice.repair_job
    cust = job.customer
    dev = job.device

    info_data = [
        [
            Paragraph(f"<b>CUSTOMER DETAILS:</b><br/><b>{cust.name}</b><br/>Phone: {cust.phone}<br/>WhatsApp: {cust.whatsapp or 'N/A'}", subtitle_style),
            Paragraph(f"<b>REPAIR JOB DETAILS:</b><br/>Job Number: <b>{job.job_number}</b><br/>Device: {dev.brand} {dev.model}<br/>IMEI: {dev.imei or 'N/A'}", subtitle_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(info_table)
    story.append(Spacer(1, 14))

    parts = job.parts_used.all()
    estimate = job.estimates.order_by('-updated_at').first()
    labor = estimate.estimated_labor_cost if estimate else 0.00

    table_data = [
        [Paragraph('<b>Description</b>', subtitle_style), Paragraph('<b>Qty</b>', subtitle_style), Paragraph('<b>Unit Price</b>', subtitle_style), Paragraph('<b>Total</b>', subtitle_style)]
    ]

    for p in parts:
        table_data.append([
            Paragraph(f"Spare Part: {p.part.name}", subtitle_style),
            Paragraph(str(p.quantity), subtitle_style),
            Paragraph("Included", subtitle_style),
            Paragraph("Included", subtitle_style),
        ])

    table_data.append([
        Paragraph("Diagnostic & Complete Repair Package", subtitle_style),
        Paragraph("1", subtitle_style),
        Paragraph(f"{settings.currency} {invoice.subtotal:,.2f}", subtitle_style),
        Paragraph(f"{settings.currency} {invoice.subtotal:,.2f}", subtitle_style),
    ])

    items_table = Table(table_data, colWidths=[270, 45, 110, 115])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 14))

    curr = settings.currency
    totals_data = [
        ['Subtotal:', f"{curr} {invoice.subtotal:,.2f}"],
        ['Discount:', f"{curr} {invoice.discount:,.2f}"],
        ['Total Bill:', f"{curr} {invoice.total:,.2f}"],
        ['Amount Paid:', f"{curr} {invoice.paid_amount:,.2f}"],
        ['Balance Due:', f"{curr} {invoice.due_amount:,.2f}"],
    ]
    totals_table = Table([[Paragraph(f"<b>{row[0]}</b>", subtitle_style), Paragraph(f"<b>{row[1]}</b>", ParagraphStyle('R', parent=subtitle_style, alignment=2))] for row in totals_data], colWidths=[380, 160])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 20))

    footer_text = Paragraph(f"<center>Thank you for choosing <b>{settings.shop_name}</b>! Quality Mobile Repairs Guaranteed.</center>", subtitle_style)
    story.append(footer_text)

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Invoice_{invoice.invoice_number}.pdf"'
    response.write(pdf)
    return response

@login_required
def invoice_image(request, pk):
    from io import BytesIO
    from django.http import HttpResponse
    from PIL import Image, ImageDraw, ImageFont
    from core.models import ShopSetting

    invoice = get_object_or_404(Invoice.objects.select_related('repair_job', 'repair_job__customer', 'repair_job__device'), pk=pk)
    settings = ShopSetting.get_settings()
    job = invoice.repair_job
    cust = job.customer
    dev = job.device

    parts = job.parts_used.all()
    estimate = job.estimates.order_by('-updated_at').first()
    labor = float(estimate.estimated_labor_cost) if estimate else 0.00

    def get_font(size, bold=False):
        font_names = ['segoeui.ttf', 'arial.ttf', 'calibri.ttf', 'DejaVuSans.ttf']
        bold_names = ['segoeuib.ttf', 'arialbd.ttf', 'calibrib.ttf', 'DejaVuSans-Bold.ttf']
        target_list = bold_names if bold else font_names
        for name in target_list:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    font_title = get_font(20, bold=True)
    font_badge = get_font(13, bold=True)
    font_bold_14 = get_font(13, bold=True)
    font_bold_12 = get_font(11, bold=True)
    font_regular_12 = get_font(11)
    font_small = get_font(10)

    item_count = len(parts) + (1 if labor > 0 else 0)
    img_w = 680
    img_h = max(720, 560 + (item_count * 28))

    img = Image.new('RGB', (img_w, img_h), color='#FFFFFF')
    draw = ImageDraw.Draw(img)

    # Accent top header bar
    draw.rectangle([(0, 0), (img_w, 10)], fill='#2563EB')

    # Header shop info
    draw.text((30, 25), (settings.shop_name or "MOBILE REPAIR SHOP").upper(), fill='#0F172A', font=font_title)
    shop_subtitle = f"Phone: {settings.shop_phone or 'N/A'}"
    if settings.shop_address:
        shop_subtitle += f" | {settings.shop_address}"
    draw.text((30, 54), shop_subtitle[:65], fill='#64748B', font=font_regular_12)

    # Right side Invoice header badge
    draw.rectangle([(440, 25), (650, 52)], fill='#EFF6FF', outline='#BFDBFE', width=1)
    draw.text((450, 31), f"INVOICE #{invoice.invoice_number}", fill='#1D4ED8', font=font_badge)
    
    date_str = invoice.created_at.strftime('%b %d, %Y')
    draw.text((450, 58), f"Date: {date_str}", fill='#64748B', font=font_regular_12)
    draw.text((450, 74), f"Job #: {job.job_number}", fill='#64748B', font=font_regular_12)

    # Divider line
    draw.line([(30, 96), (650, 96)], fill='#E2E8F0', width=2)

    # Customer & Device Overview Cards
    draw.rectangle([(30, 110), (325, 185)], fill='#F8FAFC', outline='#CBD5E1', width=1)
    draw.text((42, 118), "CUSTOMER DETAILS", fill='#64748B', font=font_small)
    draw.text((42, 134), cust.name[:28], fill='#0F172A', font=font_bold_14)
    draw.text((42, 154), f"Phone: {cust.phone}", fill='#334155', font=font_regular_12)
    if cust.whatsapp:
        draw.text((42, 168), f"WhatsApp: {cust.whatsapp}", fill='#059669', font=font_regular_12)

    draw.rectangle([(345, 110), (650, 185)], fill='#F8FAFC', outline='#CBD5E1', width=1)
    draw.text((357, 118), "REPAIR JOB & DEVICE", fill='#64748B', font=font_small)
    draw.text((357, 134), f"{dev.brand} {dev.model}"[:28], fill='#0F172A', font=font_bold_14)
    draw.text((357, 154), f"IMEI: {dev.imei or 'N/A'}", fill='#334155', font=font_regular_12)
    draw.text((357, 168), f"Complaint: {job.complaint[:30]}", fill='#64748B', font=font_regular_12)

    # Table Header
    y_tbl = 205
    draw.rectangle([(30, y_tbl), (650, y_tbl + 30)], fill='#1E293B')
    draw.text((42, y_tbl + 7), "Item Description", fill='#FFFFFF', font=font_bold_12)
    draw.text((360, y_tbl + 7), "Qty", fill='#FFFFFF', font=font_bold_12)
    draw.text((430, y_tbl + 7), "Unit Price", fill='#FFFFFF', font=font_bold_12)
    draw.text((540, y_tbl + 7), "Total", fill='#FFFFFF', font=font_bold_12)

    curr = settings.currency or "Rs."
    y_row = y_tbl + 30

    for i, p in enumerate(parts):
        bg = '#FFFFFF' if i % 2 == 0 else '#F8FAFC'
        draw.rectangle([(30, y_row), (650, y_row + 28)], fill=bg, outline='#F1F5F9', width=1)
        draw.text((42, y_row + 6), f"Spare Part: {p.part.name[:35]}", fill='#1E293B', font=font_regular_12)
        draw.text((360, y_row + 6), str(p.quantity), fill='#1E293B', font=font_regular_12)
        draw.text((430, y_row + 6), "Included", fill='#1E293B', font=font_regular_12)
        draw.text((540, y_row + 6), "Included", fill='#1E293B', font=font_bold_12)
        y_row += 28

    bg = '#FFFFFF' if len(parts) % 2 == 0 else '#F8FAFC'
    draw.rectangle([(30, y_row), (650, y_row + 28)], fill=bg, outline='#F1F5F9', width=1)
    draw.text((42, y_row + 6), "Diagnostic & Repair Package", fill='#1E293B', font=font_regular_12)
    draw.text((360, y_row + 6), "1", fill='#1E293B', font=font_regular_12)
    draw.text((430, y_row + 6), f"{curr} {invoice.subtotal:,.2f}", fill='#1E293B', font=font_regular_12)
    draw.text((540, y_row + 6), f"{curr} {invoice.subtotal:,.2f}", fill='#1E293B', font=font_bold_12)
    y_row += 28

    # Totals breakdown
    y_totals = y_row + 15
    draw.line([(30, y_totals), (650, y_totals)], fill='#E2E8F0', width=1)
    y_totals += 12

    totals_rows = [
        ("Subtotal:", f"{curr} {invoice.subtotal:,.2f}", '#475569'),
        ("Discount Applied:", f"- {curr} {invoice.discount:,.2f}", '#DC2626'),
        ("Net Total Bill:", f"{curr} {invoice.total:,.2f}", '#0F172A'),
        ("Amount Paid:", f"{curr} {invoice.paid_amount:,.2f}", '#16A34A'),
    ]

    for label, val, col in totals_rows:
        draw.text((380, y_totals), label, fill='#475569', font=font_regular_12)
        draw.text((540, y_totals), val, fill=col, font=font_bold_12)
        y_totals += 22

    # Outstanding Due box
    y_totals += 6
    is_due = invoice.due_amount > 0
    due_bg = '#FEF2F2' if is_due else '#ECFDF5'
    due_border = '#FCA5A5' if is_due else '#6EE7B7'
    due_color = '#DC2626' if is_due else '#059669'

    draw.rectangle([(360, y_totals), (650, y_totals + 40)], fill=due_bg, outline=due_border, width=1)
    draw.text((375, y_totals + 11), "OUTSTANDING DUE:", fill=due_color, font=font_bold_12)
    draw.text((530, y_totals + 11), f"{curr} {invoice.due_amount:,.2f}", fill=due_color, font=font_bold_14)

    # Footer
    y_footer = img_h - 40
    draw.line([(30, y_footer - 10), (650, y_footer - 10)], fill='#E2E8F0', width=1)
    footer_msg = f"Thank you for choosing {settings.shop_name}! Quality Mobile Repair Guaranteed."
    draw.text((100, y_footer), footer_msg[:75], fill='#64748B', font=font_regular_12)

    buf = BytesIO()
    img.save(buf, format='PNG')
    img_data = buf.getvalue()
    buf.close()

    response = HttpResponse(content_type='image/png')
    response['Content-Disposition'] = f'inline; filename="Invoice_{invoice.invoice_number}.png"'
    response.write(img_data)
    return response

