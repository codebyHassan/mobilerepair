"""
Seed command: python manage.py seed_data

Seeds the database with realistic demo data for a Pakistani mobile repair shop.
Safe to run multiple times — skips creation if data already exists.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
import random


class Command(BaseCommand):
    help = 'Seed the database with realistic demo data for the repair shop'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing data before seeding (USE WITH CAUTION)',
        )

    def handle(self, *args, **options):
        from customers.models import Customer, Device
        from repairs.models import RepairJob, Technician, RepairStatusHistory, Diagnosis, RepairEstimate
        from inventory.models import Part, InventoryTransaction, RepairPart
        from billing.models import Invoice, Payment
        from expenses.models import Expense, ExpenseCategory
        from core.models import ShopSetting
        from django.db.models import Max
        from django.contrib.auth.models import Group, Permission

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Mobile Repair Shop -- Seeding Demo Data ===\n'))

        # Configure Auth Groups & Permissions
        group_roles = {
            'Technician': [
                'view_repairjob', 'change_repairjob', 'view_part', 'change_part', 'view_customer', 'view_device'
            ],
            'Receptionist': [
                'view_customer', 'add_customer', 'change_customer',
                'view_device', 'add_device', 'change_device',
                'view_repairjob', 'add_repairjob', 'change_repairjob',
                'view_invoice', 'add_invoice', 'change_invoice',
                'view_payment', 'add_payment',
            ],
            'Accountant': [
                'view_invoice', 'add_invoice', 'change_invoice',
                'view_payment', 'add_payment', 'change_payment',
                'view_expense', 'add_expense', 'change_expense',
                'view_expensecategory',
            ],
            'Shop Manager': [p.codename for p in Permission.objects.all()]
        }

        for role_name, codenames in group_roles.items():
            grp, _ = Group.objects.get_or_create(name=role_name)
            perms = Permission.objects.filter(codename__in=codenames)
            grp.permissions.set(perms)
        self.stdout.write(self.style.SUCCESS('  [+] Configured 4 Auth Groups (Technician, Receptionist, Accountant, Shop Manager)'))

        if options['clear']:
            self.stdout.write(self.style.WARNING('  [!] Clearing existing data...'))
            Payment.objects.all().delete()
            Invoice.objects.all().delete()
            RepairPart.objects.all().delete()
            InventoryTransaction.objects.all().delete()
            RepairStatusHistory.objects.all().delete()
            RepairEstimate.objects.all().delete()
            Diagnosis.objects.all().delete()
            RepairJob.objects.all().delete()
            Part.objects.all().delete()
            Device.objects.all().delete()
            Customer.objects.all().delete()
            Expense.objects.all().delete()
            ExpenseCategory.objects.all().delete()
            Technician.objects.all().delete()
            self.stdout.write(self.style.WARNING('  [done] Cleared.\n'))

        # ── 1. Shop Settings ─────────────────────────────────────────────────
        settings = ShopSetting.get_settings()
        if settings.shop_name == 'My Repair Shop':
            settings.shop_name = 'TechCare Mobile Repairs'
            settings.shop_phone = '0300-1234567'
            settings.shop_address = 'Shop #12, Al-Hamra Plaza, Main Boulevard, Gulberg III, Lahore'
            settings.currency = 'Rs.'
            settings.invoice_prefix = 'INV'
            settings.job_prefix = 'JOB'
            settings.save()
            self.stdout.write(self.style.SUCCESS('  [+] Shop settings configured.'))

        # ── 2. Superuser ─────────────────────────────────────────────────────
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@techcare.pk', 'admin123')
            self.stdout.write(self.style.SUCCESS('  [+] Admin user created (admin / admin123)'))

        # ── 3. Technicians ───────────────────────────────────────────────────
        techs_data = [
            ('Usman Malik', '0321-5551234', 'iPhone & Samsung specialist'),
            ('Bilal Ahmed', '0333-4449876', 'Screen replacement & charging ports'),
            ('Kashif Raza', '0311-7778899', 'Motherboard repair & micro-soldering'),
        ]
        technicians = []
        for name, phone, spec in techs_data:
            t, created = Technician.objects.get_or_create(
                name=name,
                defaults={'phone': phone, 'specialization': spec, 'status': 'active'}
            )
            technicians.append(t)
        self.stdout.write(self.style.SUCCESS(f'  [+] {len(techs_data)} technicians ready.'))

        # ── 4. Customers ─────────────────────────────────────────────────────
        customers_data = [
            ('Ali Hassan', '0300-1112233', '0300-1112233', 'ali.hassan@gmail.com'),
            ('Sara Khan', '0311-4445566', '0311-4445566', 'sara.khan@hotmail.com'),
            ('Muhammad Tariq', '0321-7778899', None, None),
            ('Fatima Bibi', '0333-2223344', '0333-2223344', None),
            ('Ahmed Nawaz', '0345-9990011', None, 'ahmed.nawaz@gmail.com'),
            ('Zainab Rashid', '0300-6667788', '0300-6667788', None),
            ('Imran Siddiqui', '0311-1234567', None, None),
            ('Hina Mirza', '0321-9876543', '0321-9876543', 'hina.mirza@yahoo.com'),
            ('Asad Butt', '0333-8887766', None, None),
            ('Nadia Iqbal', '0345-5554433', '0345-5554433', None),
        ]
        customers = []
        for name, phone, whatsapp, email in customers_data:
            c, _ = Customer.objects.get_or_create(
                phone=phone,
                defaults={'name': name, 'whatsapp': whatsapp, 'email': email,
                          'address': f'Lahore, Pakistan'}
            )
            customers.append(c)
        self.stdout.write(self.style.SUCCESS(f'  [+] {len(customers_data)} customers ready.'))

        # ── 5. Devices ───────────────────────────────────────────────────────
        devices_data = [
            (customers[0], 'Apple', 'iPhone 14 Pro', '351234567890001', 'Deep Purple', '256GB'),
            (customers[0], 'Apple', 'iPhone 12', '351234567890002', 'White', '128GB'),
            (customers[1], 'Samsung', 'Galaxy S23 Ultra', '359876543210001', 'Phantom Black', '256GB'),
            (customers[2], 'OnePlus', '11 5G', '358765432100001', 'Titan Black', '256GB'),
            (customers[3], 'Apple', 'iPhone 13', '352345678900001', 'Midnight', '128GB'),
            (customers[4], 'Xiaomi', 'Redmi Note 12 Pro', '357654321000001', 'Glacier Blue', '128GB'),
            (customers[5], 'Samsung', 'Galaxy A54', '356543210000001', 'Awesome White', '128GB'),
            (customers[6], 'Apple', 'iPhone 11', '355432100000001', 'Yellow', '64GB'),
            (customers[7], 'Vivo', 'V25 Pro', '354321000000001', 'Starlight Blue', '256GB'),
            (customers[8], 'OPPO', 'Reno 8 Pro', '353210000000001', 'Glazed Black', '256GB'),
            (customers[9], 'Apple', 'iPhone 15', '352100000000001', 'Pink', '128GB'),
        ]
        devices = []
        for cust, brand, model, imei, color, storage in devices_data:
            d, _ = Device.objects.get_or_create(
                imei=imei,
                defaults={
                    'customer': cust, 'brand': brand, 'model': model,
                    'color': color, 'storage': storage,
                    'physical_condition': 'Minor scratches on screen edges'
                }
            )
            devices.append(d)
        self.stdout.write(self.style.SUCCESS(f'  [+] {len(devices_data)} devices registered.'))

        # ── 6. Parts Inventory ───────────────────────────────────────────────
        parts_data = [
            ('iPhone 14 Pro Screen OLED', 'IPH14PRO-SCR', 'Apple', 'iPhone 14 Pro', 'Screen', Decimal('22000'), Decimal('32000'), 8, 2),
            ('iPhone 13 Screen OLED', 'IPH13-SCR', 'Apple', 'iPhone 13', 'Screen', Decimal('16000'), Decimal('24000'), 10, 2),
            ('iPhone 12 Screen LCD', 'IPH12-SCR', 'Apple', 'iPhone 12', 'Screen', Decimal('12000'), Decimal('18000'), 12, 3),
            ('iPhone 11 Screen LCD', 'IPH11-SCR', 'Apple', 'iPhone 11', 'Screen', Decimal('9000'), Decimal('14000'), 15, 3),
            ('iPhone 15 Screen OLED', 'IPH15-SCR', 'Apple', 'iPhone 15', 'Screen', Decimal('28000'), Decimal('40000'), 5, 2),
            ('Samsung S23 Ultra Screen', 'SAMS23U-SCR', 'Samsung', 'Galaxy S23 Ultra', 'Screen', Decimal('18000'), Decimal('28000'), 4, 2),
            ('Samsung A54 Screen', 'SAMA54-SCR', 'Samsung', 'Galaxy A54', 'Screen', Decimal('8000'), Decimal('13000'), 6, 2),
            ('iPhone 14 Pro Battery', 'IPH14PRO-BAT', 'Apple', 'iPhone 14 Pro', 'Battery', Decimal('2500'), Decimal('4500'), 20, 5),
            ('iPhone 13 Battery', 'IPH13-BAT', 'Apple', 'iPhone 13', 'Battery', Decimal('2000'), Decimal('3500'), 25, 5),
            ('Samsung S23 Ultra Battery', 'SAMS23U-BAT', 'Samsung', 'Galaxy S23 Ultra', 'Battery', Decimal('2800'), Decimal('5000'), 15, 5),
            ('iPhone Charging Port Lightning', 'IPH-CHRG-LTG', 'Apple', 'iPhone 11/12/13', 'Charging Port', Decimal('800'), Decimal('1800'), 30, 10),
            ('iPhone USB-C Charging Port', 'IPH-CHRG-C', 'Apple', 'iPhone 15', 'Charging Port', Decimal('1200'), Decimal('2500'), 20, 5),
            ('Redmi Note 12 Pro Screen', 'RDMI12P-SCR', 'Xiaomi', 'Redmi Note 12 Pro', 'Screen', Decimal('6000'), Decimal('10000'), 8, 2),
            ('OnePlus 11 Screen AMOLED', 'OP11-SCR', 'OnePlus', 'OnePlus 11', 'Screen', Decimal('14000'), Decimal('22000'), 3, 1),
            ('Universal Back Glass iPhone', 'IPH-BACK-GLASS', 'Generic', 'Universal iPhone', 'Back Glass', Decimal('1500'), Decimal('3500'), 50, 10),
            ('Thermal Paste 1g Syringe', 'THERM-PASTE-1G', 'Generic', 'Universal', 'Consumable', Decimal('200'), Decimal('500'), 100, 20),
        ]
        parts = []
        admin_user = User.objects.filter(is_superuser=True).first()
        for name, sku, brand, compat, cat, cost, price, stock, min_stock in parts_data:
            p, created = Part.objects.get_or_create(
                sku=sku,
                defaults={
                    'name': name, 'brand': brand, 'compatible_device': compat,
                    'category': cat, 'purchase_cost': cost, 'selling_price': price,
                    'current_stock': stock, 'minimum_stock': min_stock,
                    'supplier': 'Mobile Parts Market, Hall Road Lahore'
                }
            )
            if created:
                InventoryTransaction.objects.create(
                    part=p, transaction_type='purchase', quantity=stock,
                    note='Initial stock purchase',
                    created_by=admin_user
                )
            parts.append(p)
        self.stdout.write(self.style.SUCCESS(f'  [+] {len(parts_data)} parts seeded.'))

        # ── 7. Repair Jobs ───────────────────────────────────────────────────
        from repairs.views import generate_job_number, recalculate_repair_bill

        today = timezone.localtime(timezone.now()).date()

        jobs_spec = [
            # (device_idx, complaint, status, technician_idx, parts_idx_list, labor, advance_paid)
            (0,  'Screen cracked, touch not working',              'DELIVERED',       0, [0], Decimal('2000'), Decimal('34000')),
            (2,  'Battery draining too fast, overheating',         'DELIVERED',       1, [9], Decimal('1500'), Decimal('6500')),
            (4,  'Screen broken, need replacement',                 'READY_FOR_PICKUP',2, [1], Decimal('2000'), Decimal('20000')),
            (6,  'Phone not charging at all',                       'REPAIRING',      1, [10], Decimal('500'),  Decimal('0')),
            (7,  'Screen flickering and display lines appear',      'DIAGNOSING',     0, [],   Decimal('0'),    Decimal('0')),
            (3,  'Back glass shattered after drop',                 'DELIVERED',       0, [14], Decimal('800'),  Decimal('4300')),
            (5,  'Redmi touchscreen unresponsive at bottom part',   'WAITING_PARTS',  2, [],   Decimal('0'),    Decimal('0')),
            (8,  'Vivo camera not working, black screen on open',   'RECEIVED',       None, [], Decimal('0'),   Decimal('0')),
            (9,  'OPPO not turning on after water damage',          'DIAGNOSING',     2, [],   Decimal('0'),    Decimal('5000')),
            (10, 'iPhone 15 charging port loose, intermittent',     'REPAIRING',      0, [11], Decimal('1000'), Decimal('0')),
        ]

        created_jobs = []
        for idx, (dev_i, complaint, status, tech_i, part_idxs, labor, advance) in enumerate(jobs_spec):
            dev = devices[dev_i]
            cust = dev.customer

            if RepairJob.objects.filter(device=dev, status=status).exists():
                existing = RepairJob.objects.filter(device=dev, status=status).first()
                created_jobs.append(existing)
                continue

            job = RepairJob.objects.create(
                job_number=generate_job_number(),
                customer=cust,
                device=dev,
                complaint=complaint,
                physical_condition='Visible external damage',
                accessories='Original box not available',
                status=status,
                priority=random.choice(['low', 'medium', 'high']),
                assigned_technician=technicians[tech_i] if tech_i is not None else None,
            )
            RepairStatusHistory.objects.create(
                repair_job=job, old_status=None, new_status='RECEIVED',
                changed_by=admin_user, note='Job intake registered'
            )

            # Diagnosis
            Diagnosis.objects.create(
                repair_job=job,
                technician_diagnosis=f'Inspected {dev.brand} {dev.model}. {complaint}',
                recommended_repair='Replacement required' if part_idxs else 'Needs further diagnosis'
            )

            # Estimate
            est_cost = (sum(parts[pi].selling_price for pi in part_idxs) if part_idxs else Decimal('0')) + labor
            RepairEstimate.objects.create(
                repair_job=job,
                estimated_cost=est_cost,
                status='approved' if status not in ['RECEIVED', 'DIAGNOSING'] else 'pending'
            )

            # Invoice
            max_inv = Invoice.objects.aggregate(m=Max('id'))['m'] or 0
            inv_num = f"INV-2026-{(max_inv + 1):05d}"
            invoice = Invoice.objects.create(
                invoice_number=inv_num,
                repair_job=job,
                subtotal=Decimal('0.00'),
                discount=Decimal('0.00')
            )

            # Consume parts
            for pi in part_idxs:
                p = parts[pi]
                if p.current_stock > 0:
                    p.current_stock -= 1
                    p.save()
                    InventoryTransaction.objects.create(
                        part=p, transaction_type='repair_use', quantity=-1,
                        repair_job=job, note=f'Used in {job.job_number}',
                        created_by=admin_user
                    )
                    RepairPart.objects.create(
                        repair_job=job, part=p, quantity=1,
                        purchase_cost=p.purchase_cost,
                        customer_price=p.selling_price
                    )

            recalculate_repair_bill(job)
            invoice.refresh_from_db()

            if advance > 0:
                actual_advance = min(advance, invoice.total)
                if actual_advance > 0:
                    Payment.objects.create(
                        invoice=invoice,
                        amount=actual_advance,
                        payment_method='cash',
                        notes='Advance payment on intake',
                        received_by=admin_user
                    )
                    invoice.refresh_from_db()

            if status in ('DELIVERED', 'READY_FOR_PICKUP') and invoice.due_amount > 0:
                Payment.objects.create(
                    invoice=invoice,
                    amount=invoice.due_amount,
                    payment_method='cash',
                    notes='Final payment on delivery',
                    received_by=admin_user
                )

            if status != 'RECEIVED':
                RepairStatusHistory.objects.create(
                    repair_job=job, old_status='RECEIVED', new_status=status,
                    changed_by=admin_user, note='Status updated'
                )

            created_jobs.append(job)

        self.stdout.write(self.style.SUCCESS(f'  [+] {len(jobs_spec)} repair jobs seeded.'))

        # ── 8. Expense Categories & Expenses ─────────────────────────────────
        categories_data = ['Rent', 'Electricity', 'Internet', 'Staff Salary', 'Equipment', 'Miscellaneous']
        categories = {}
        for cat_name in categories_data:
            cat, _ = ExpenseCategory.objects.get_or_create(name=cat_name)
            categories[cat_name] = cat

        expenses_data = [
            ('Rent', Decimal('35000'), 'cash', today.replace(day=1), 'Monthly shop rent - August 2026'),
            ('Electricity', Decimal('8500'), 'cash', today.replace(day=5) if today.day >= 5 else today, 'LESCO electricity bill'),
            ('Internet', Decimal('2500'), 'cash', today.replace(day=3) if today.day >= 3 else today, 'Fiber internet monthly'),
            ('Staff Salary', Decimal('45000'), 'bank', today.replace(day=1), 'Tech salaries for August'),
            ('Equipment', Decimal('12000'), 'cash', today, 'New soldering station and hot air gun'),
            ('Miscellaneous', Decimal('3200'), 'cash', today, 'Cleaning supplies and consumables'),
        ]
        exp_count = 0
        for cat_name, amount, method, date, desc in expenses_data:
            if not Expense.objects.filter(category=categories[cat_name], date=date).exists():
                Expense.objects.create(
                    category=categories[cat_name],
                    amount=amount,
                    payment_method=method,
                    date=date,
                    description=desc
                )
                exp_count += 1
        self.stdout.write(self.style.SUCCESS(f'  [+] {exp_count} expenses logged.'))

        # ── 9. Summary ───────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('  [OK] Seeding complete! Summary:'))
        self.stdout.write(f'     Customers : {Customer.objects.count()}')
        self.stdout.write(f'     Devices   : {Device.objects.count()}')
        self.stdout.write(f'     Parts     : {Part.objects.count()}')
        self.stdout.write(f'     Jobs      : {RepairJob.objects.count()}')
        self.stdout.write(f'     Invoices  : {Invoice.objects.count()}')
        self.stdout.write(f'     Payments  : {Payment.objects.count()}')
        self.stdout.write(f'     Expenses  : {Expense.objects.count()}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('  Login -> http://127.0.0.1:8000/  |  admin / admin123'))
        self.stdout.write('')
