from django.test import TestCase
from django.contrib.auth.models import User
from customers.models import Customer, Device
from repairs.models import RepairJob, RepairEstimate, Diagnosis, Technician
from inventory.models import Part, RepairPart, InventoryTransaction
from billing.models import Invoice, Payment
from core.models import ShopSetting
from decimal import Decimal
from django.db.models import Sum, F

class RepairWorkflowTestCase(TestCase):
    def setUp(self):
        # Create superuser / staff user for admin testing
        self.user = User.objects.create_superuser(username='admin', password='password', email='admin@example.com')
        # Initialize default settings
        self.settings = ShopSetting.get_settings()
        
    def test_complete_repair_workflow(self):
        # 1. Customer intake
        customer = Customer.objects.create(
            name="Ali Khan",
            phone="03001234567"
        )
        
        # 2. Device intake
        device = Device.objects.create(
            customer=customer,
            brand="Apple",
            model="iPhone 13",
            imei="123456789012345",
            physical_condition="Broken screen",
            accessories_received="SIM Tray"
        )
        
        # 3. Create repair job
        from repairs.views import generate_job_number, recalculate_repair_bill
        job = RepairJob.objects.create(
            job_number=generate_job_number(),
            customer=customer,
            device=device,
            complaint="Broken screen",
            physical_condition=device.physical_condition,
            accessories=device.accessories_received
        )
        
        # 4. Check initial empty diagnosis & estimate & invoice
        diagnosis = Diagnosis.objects.create(repair_job=job, technician_diagnosis='', recommended_repair='')
        estimate = RepairEstimate.objects.create(repair_job=job, estimated_cost=Decimal('0.00'))
        
        invoice = Invoice.objects.create(
            invoice_number="INV-2026-00001",
            repair_job=job,
            subtotal=0.00,
            discount=0.00
        )
        
        # 5. Inventory: setup iPhone 13 Screen part
        part = Part.objects.create(
            name="iPhone 13 Screen",
            sku="IPH13-SCR",
            brand="OEM",
            compatible_device="iPhone 13",
            category="Screen",
            purchase_cost=Decimal("12000.00"),
            selling_price=Decimal("18000.00"),
            current_stock=5,
            minimum_stock=2
        )
        
        # 6. Technical Diagnosis & Estimate update (All-Inclusive Customer Quote: Rs. 20,000)
        diagnosis.technician_diagnosis = "LCD display assembly damaged."
        diagnosis.recommended_repair = "Replace screen assembly."
        diagnosis.save()
        
        estimate.estimated_cost = Decimal("20000.00")
        estimate.save()
        
        # 7. Issue Part to Repair Job
        part.current_stock -= 1
        part.save()
        
        # Log inventory transaction
        InventoryTransaction.objects.create(
            part=part,
            transaction_type='repair_use',
            quantity=-1,
            repair_job=job,
            note="Used in screen repair",
            created_by=self.user
        )
        
        # Link part to job
        RepairPart.objects.create(
            repair_job=job,
            part=part,
            quantity=1,
            purchase_cost=part.purchase_cost,
            customer_price=part.selling_price
        )
        
        # Recalculate bill
        recalculate_repair_bill(job)
        invoice.refresh_from_db()
        
        # Assertions: invoice subtotal is locked to the all-inclusive diagnostic estimate (Rs. 20,000)
        self.assertEqual(invoice.subtotal, Decimal("20000.00"))
        self.assertEqual(invoice.total, Decimal("20000.00"))
        self.assertEqual(invoice.due_amount, Decimal("20000.00"))
        
        # 8. Record Advance payment: Rs. 5,000
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("5000.00"),
            payment_method='cash',
            received_by=self.user
        )
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("5000.00"))
        self.assertEqual(invoice.due_amount, Decimal("15000.00"))
        
        # 9. Record final payment: Rs. 15,000
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("15000.00"),
            payment_method='cash',
            received_by=self.user
        )
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("20000.00"))
        self.assertEqual(invoice.due_amount, Decimal("0.00"))
        
        # 10. Update job status to DELIVERED
        job.status = 'DELIVERED'
        job.save()
        
        # Verify final system state
        part.refresh_from_db()
        self.assertEqual(part.current_stock, 4) # Stock decreased by 1
        
        # Profit margin assertion
        parts_cost = job.parts_used.aggregate(
            cost=Sum(F('purchase_cost') * F('quantity'))
        )['cost'] or 0.00
        self.assertEqual(parts_cost, Decimal("12000.00"))
        
        total_bill = invoice.total
        profit = total_bill - parts_cost
        self.assertEqual(profit, Decimal("8000.00"))

    def test_live_customer_search_and_devices_api(self):
        self.client.force_login(self.user)
        c = Customer.objects.create(name="Tariq Mahmood", phone="03129876543")
        dev = Device.objects.create(customer=c, brand="Samsung", model="Galaxy S23", imei="999888777666555")
        
        # 1. Test live search API with empty query (returns recent customers)
        response = self.client.get('/api/search/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(len(data['customers']) > 0)
        self.assertEqual(data['customers'][0]['name'], "Tariq Mahmood")
        
        # 2. Test live search API with single character query "t"
        response_q = self.client.get('/api/search/?q=t')
        self.assertEqual(response_q.status_code, 200)
        data_q = response_q.json()
        self.assertTrue(len(data_q['customers']) > 0)
        
        # 3. Test customer devices API
        response_dev = self.client.get(f'/customers/api/devices/{c.id}/')
        self.assertEqual(response_dev.status_code, 200)
        data_dev = response_dev.json()
        self.assertEqual(data_dev['customer']['name'], "Tariq Mahmood")
        self.assertEqual(len(data_dev['devices']), 1)
        # 4. Test customer with NO repair jobs (outstanding_due is None in SQL)
        c_nojobs = Customer.objects.create(name="New Customer No Jobs", phone="03990001122")
        response_nojobs = self.client.get('/api/search/?q=New')
        self.assertEqual(response_nojobs.status_code, 200)
        data_nojobs = response_nojobs.json()
        self.assertEqual(len(data_nojobs['customers']), 1)
        self.assertEqual(data_nojobs['customers'][0]['name'], "New Customer No Jobs")

    def test_all_admin_views(self):
        self.client.force_login(self.user)
        admin_urls = [
            '/admin/',
            '/admin/core/shopsetting/',
            '/admin/customers/customer/',
            '/admin/customers/device/',
            '/admin/repairs/technician/',
            '/admin/repairs/repairjob/',
            '/admin/repairs/repairstatushistory/',
            '/admin/repairs/diagnosis/',
            '/admin/repairs/repairestimate/',
            '/admin/inventory/part/',
            '/admin/inventory/inventorytransaction/',
            '/admin/inventory/repairpart/',
            '/admin/billing/invoice/',
            '/admin/billing/payment/',
            '/admin/expenses/expensecategory/',
            '/admin/expenses/expense/',
        ]
        for url in admin_urls:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, f"Failed on admin url {url}")

    def test_repair_detail_view(self):
        self.client.force_login(self.user)
        c = Customer.objects.create(name="Detail Test Cust", phone="03881112233")
        dev = Device.objects.create(customer=c, brand="Xiaomi", model="Redmi 12")
        from repairs.views import generate_job_number
        job = RepairJob.objects.create(job_number=generate_job_number(), customer=c, device=dev, complaint="Display blank")
        response = self.client.get(f'/repairs/view/{job.id}/', follow=True)
        self.assertEqual(response.status_code, 200)

    def test_superadmin_lifecycle_unrestricted_editing(self):
        self.client.force_login(self.user)
        c = Customer.objects.create(name="Lifecycle Superadmin Cust", phone="03991234567")
        dev = Device.objects.create(customer=c, brand="Apple", model="iPhone 14")
        from repairs.views import generate_job_number
        job = RepairJob.objects.create(job_number=generate_job_number(), customer=c, device=dev, complaint="Camera cracked")
        
        # 1. Superadmin can navigate to any stage directly
        res = self.client.get(f'/repairs/lifecycle/{job.id}/stage/WARRANTY/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Warranty")

        # 2. Superadmin can edit Stage 1 (Customer & Device) in-place
        res = self.client.post(f'/repairs/lifecycle/{job.id}/stage/CUSTOMER/', {
            'stage_code': 'CUSTOMER',
            'action': 'save_stage',
            'customer_mode': 'edit',
            'name': 'Updated Superadmin Cust',
            'phone': '03991234567',
            'whatsapp': '03991234567',
            'device_mode': 'edit',
            'brand': 'Apple Pro',
            'model': 'iPhone 14 Pro',
            'complaint': 'Camera and back glass cracked'
        })
        self.assertEqual(res.status_code, 302)
        c.refresh_from_db()
        dev.refresh_from_db()
        self.assertEqual(c.name, 'Updated Superadmin Cust')
        self.assertEqual(dev.brand, 'Apple Pro')

        # 3. Superadmin can edit Stage 3 (Diagnosis & Single Estimate)
        res = self.client.post(f'/repairs/lifecycle/{job.id}/stage/DIAGNOSIS/', {
            'stage_code': 'DIAGNOSIS',
            'action': 'save_stage',
            'technician_diagnosis': 'Cracked camera lens and back panel',
            'recommended_repair': 'Replace camera and housing',
            'estimated_cost': '6000.00',
        })
        self.assertEqual(res.status_code, 302)
        est = job.estimates.order_by('-updated_at').first()
        self.assertEqual(est.estimated_cost, Decimal('6000.00'))

        # 4. Server-Side Validation: empty estimated_cost must be rejected
        res_empty = self.client.post(f'/repairs/lifecycle/{job.id}/stage/DIAGNOSIS/', {
            'stage_code': 'DIAGNOSIS',
            'action': 'save_stage',
            'technician_diagnosis': 'Cracked camera lens and back panel',
            'recommended_repair': 'Replace camera and housing',
            'estimated_cost': '',
        }, follow=True)
        self.assertEqual(res_empty.status_code, 200)
        self.assertContains(res_empty, "Estimated Cost is required")

        # 5. Server-Side Validation: negative estimated_cost must be rejected
        res_neg = self.client.post(f'/repairs/lifecycle/{job.id}/stage/DIAGNOSIS/', {
            'stage_code': 'DIAGNOSIS',
            'action': 'save_stage',
            'technician_diagnosis': 'Cracked camera lens and back panel',
            'recommended_repair': 'Replace camera and housing',
            'estimated_cost': '-100.00',
        }, follow=True)
        self.assertEqual(res_neg.status_code, 200)
        self.assertContains(res_neg, "Estimated Cost cannot be negative")

    def test_invoice_pdf_view(self):
        self.client.force_login(self.user)
        c = Customer.objects.create(name="PDF Test Cust", phone="03881112234")
        dev = Device.objects.create(customer=c, brand="Samsung", model="S23")
        from repairs.views import generate_job_number
        from billing.models import Invoice
        job = RepairJob.objects.create(job_number=generate_job_number(), customer=c, device=dev, complaint="Battery dead")
        inv = Invoice.objects.create(invoice_number="INV-PDF-001", repair_job=job, subtotal=5000, total=5000, due_amount=5000)
        res = self.client.get(f'/billing/invoice/{inv.id}/pdf/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/pdf')



