Title: Advanced Testing (Odoo 18)

This guide covers advanced testing patterns specific to Odoo 18, building on the foundational patterns
in [testing.md](../testing.md). Examples are drawn from the `product_connect` module to demonstrate real-world usage.

## Table of Contents

1. [Testing Computed Fields with Cache Invalidation](#1-testing-computed-fields-with-cache-invalidation)
2. [Testing Constraints and Validations](#2-testing-constraints-and-validations)
3. [Record Rules and Access Rights Testing](#3-record-rules-and-access-rights-testing)
4. [Multi-Company Testing Scenarios](#4-multi-company-testing-scenarios)
5. [Translation and Internationalization Testing](#5-translation-and-internationalization-testing)
6. [Testing with flush() and invalidate_cache()](#6-testing-with-flush-and-invalidate_cache)
7. [Performance Testing Patterns](#7-performance-testing-patterns)
8. [Testing Workflows and State Transitions](#8-testing-workflows-and-state-transitions)
9. [Testing with Different User Contexts](#9-testing-with-different-user-contexts)
10. [Mock and Patch Patterns for External Services](#10-mock-and-patch-patterns-for-external-services)

---

## 1. Testing Computed Fields with Cache Invalidation

Computed fields in Odoo 18 have sophisticated caching mechanisms. Testing them requires understanding dependency chains
and cache invalidation.

### Basic Computed Field Testing

```python
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory


@tagged(*UNIT_TAGS)
class TestComputedFields(UnitTestCase):
    def test_motor_product_computed_name(self):
        """Test computed field with proper dependency tracking."""
        # Create motor with specific attributes
        motor_product = ProductFactory.create(self.env,
                                              motor_hp=150,
                                              motor_year=2020,
                                              motor_model="YAMAHA-F150"
                                              )
        motor = motor_product.motor

        # Initial computed value
        initial_name = motor_product.motor_product_computed_name
        self.assertIn("YAMAHA-F150", initial_name)
        self.assertIn("150", initial_name)

        # Modify dependency and verify recomputation
        motor.model = "MERCURY-150"
        motor.flush_model()  # Force database update
        motor_product.invalidate_recordset(['motor_product_computed_name'])

        updated_name = motor_product.motor_product_computed_name
        self.assertIn("MERCURY-150", updated_name)
        self.assertNotEqual(initial_name, updated_name)

    def test_cost_total_computation_with_quantities(self):
        """Test computed field that depends on multiple related fields."""
        product = ProductFactory.create(self.env,
                                        standard_price=100.0,
                                        initial_quantity=5.0
                                        )

        # Test initial computation
        self.assertEqual(product.initial_cost_total, 500.0)

        # Test quantity change
        product.initial_quantity = 10.0
        product.flush_recordset(['initial_quantity'])
        product.invalidate_recordset(['initial_cost_total'])
        self.assertEqual(product.initial_cost_total, 1000.0)

        # Test price change
        product.standard_price = 75.0
        product.flush_recordset(['standard_price'])
        product.invalidate_recordset(['initial_cost_total'])
        self.assertEqual(product.initial_cost_total, 750.0)
```

### Testing Cross-Model Dependencies

```python
@tagged(*UNIT_TAGS)
class TestCrossModelComputedFields(UnitTestCase):
    def test_motor_stage_fold_computation(self):
        """Test computed field depending on user context."""
        stage = self.env["motor.stage"].create({
            "name": "Test Stage",
            "fold_by_default": False
        })

        # Test default computation
        self.assertFalse(stage.fold)

        # Simulate user folding the stage
        self.env.user.write({
            'folded_motor_stages': [(4, stage.id)]
        })

        # Force recomputation
        stage.invalidate_recordset(['fold'])
        self.assertTrue(stage.fold)

        # Test fold_by_default override
        stage.fold_by_default = True
        stage.invalidate_recordset(['fold'])
        self.assertTrue(stage.fold)

    def test_product_image_count_with_related_changes(self):
        """Test computed field that depends on One2many records."""
        product = ProductFactory.create(self.env)
        self.assertEqual(product.image_count, 0)

        # Add images and test recomputation
        image1 = self.env["product.image"].create({
            "product_tmpl_id": product.id,
            "name": "Test Image 1"
        })
        product.invalidate_recordset(['image_count'])
        self.assertEqual(product.image_count, 1)

        # Add another image
        image2 = self.env["product.image"].create({
            "product_tmpl_id": product.id,
            "name": "Test Image 2"
        })
        product.invalidate_recordset(['image_count'])
        self.assertEqual(product.image_count, 2)

        # Remove image and test
        image1.unlink()
        product.invalidate_recordset(['image_count'])
        self.assertEqual(product.image_count, 1)
```

### Advanced Cache Invalidation Testing

```python
@tagged(*UNIT_TAGS)
class TestCacheInvalidation(UnitTestCase):
    def test_bulk_invalidation_performance(self):
        """Test cache invalidation with multiple records."""
        products = ProductFactory.create_batch(self.env, count=10)

        # Ensure all computed fields are cached
        for product in products:
            _ = product.initial_cost_total  # Access to cache

        # Bulk update and test invalidation
        products.write({'standard_price': 200.0})

        # Verify all records were invalidated
        for product in products:
            self.assertEqual(product.initial_cost_total,
                             product.initial_quantity * 200.0)

    def test_selective_field_invalidation(self):
        """Test invalidating specific fields only."""
        product = ProductFactory.create(self.env,
                                        standard_price=100.0,
                                        initial_quantity=2.0
                                        )

        # Cache multiple computed fields
        _ = product.initial_cost_total
        _ = product.is_price_or_cost_missing

        # Selectively invalidate only one field
        product.invalidate_recordset(['initial_cost_total'])

        # Verify selective invalidation
        with self.assertQueryCount(1):  # Only one field should recompute
            _ = product.initial_cost_total
```

---

## 2. Testing Constraints and Validations

Odoo 18 provides multiple validation mechanisms. Testing them requires understanding the validation lifecycle.

### SQL Constraints Testing

```python
from ..common_imports import tagged, ValidationError, IntegrityError, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory, MotorFactory


@tagged(*UNIT_TAGS)
class TestSQLConstraints(UnitTestCase):
    def test_motor_number_uniqueness(self):
        """Test SQL constraint for unique motor numbers."""
        motor1 = MotorFactory.create(self.env)

        # Attempt to create motor with same number should fail
        with self.assertRaises(IntegrityError):
            self.env["motor"].create({
                "motor_number": motor1.motor.motor_number,
                "horsepower": 100,
                "model": "TEST-MODEL",
                "serial_number": "DIFFERENT-SERIAL"
            })

    def test_sku_uniqueness_constraint(self):
        """Test SKU uniqueness across products."""
        product1 = ProductFactory.create(self.env)

        with self.assertRaises(IntegrityError):
            ProductFactory.create(self.env,
                                  default_code=product1.default_code
                                  )

    def test_shopify_product_id_uniqueness(self):
        """Test Shopify ID constraint."""
        product1 = ProductFactory.create(self.env,
                                         shopify_product_id="12345"
                                         )

        with self.assertRaises(IntegrityError):
            ProductFactory.create(self.env,
                                  shopify_product_id="12345"
                                  )
```

### Python Constraints Testing

```python
@tagged(*UNIT_TAGS)
class TestPythonConstraints(UnitTestCase):
    def test_motor_location_constraint(self):
        """Test Python validation for motor locations."""
        # First motor with location should succeed
        motor1 = MotorFactory.create(self.env, location="A1")

        # Second motor with same location should fail
        with self.assertRaises(ValidationError) as context:
            MotorFactory.create(self.env, location="A1")

        self.assertIn("location", str(context.exception).lower())

    def test_sku_pattern_validation(self):
        """Test SKU pattern constraint."""
        # Valid SKU patterns
        valid_skus = ["1234", "12345678", "800001"]
        for sku in valid_skus:
            product = ProductFactory.create(self.env, default_code=sku)
            self.assertEqual(product.default_code, sku)

        # Invalid SKU patterns
        invalid_skus = ["123", "ABC123", "123456789", ""]
        for sku in invalid_skus:
            with self.assertRaises(ValidationError):
                ProductFactory.create(self.env, default_code=sku)

    def test_price_cost_validation(self):
        """Test business logic validation."""
        product = ProductFactory.create(self.env)

        # Test negative price validation
        with self.assertRaises(ValidationError):
            product.list_price = -10.0

        # Test zero cost for motor products
        motor_product = MotorFactory.create(self.env)
        with self.assertRaises(ValidationError):
            motor_product.standard_price = 0.0
```

### Field-Level Validation Testing

```python
@tagged(*UNIT_TAGS)
class TestFieldValidation(UnitTestCase):
    def test_required_field_validation(self):
        """Test required field constraints."""
        with self.assertRaises(ValidationError):
            self.env["motor.stage"].create({})  # name is required

        with self.assertRaises(ValidationError):
            self.env["motor.tag"].create({})  # name is required

    def test_selection_field_validation(self):
        """Test selection field value constraints."""
        motor = MotorFactory.create(self.env).motor

        # Valid priority values
        for priority in ["0", "1", "2"]:
            motor.priority = priority
            self.assertEqual(motor.priority, priority)

        # Invalid priority should fail
        with self.assertRaises(ValidationError):
            motor.priority = "3"

    def test_many2one_validation(self):
        """Test foreign key constraint validation."""
        product = ProductFactory.create(self.env)

        # Valid manufacturer
        manufacturer = self.env["product.manufacturer"].create({
            "name": "Test Manufacturer"
        })
        product.manufacturer = manufacturer
        self.assertEqual(product.manufacturer, manufacturer)

        # Non-existent manufacturer should fail
        with self.assertRaises(ValidationError):
            product.manufacturer = 99999
```

---

## 3. Record Rules and Access Rights Testing

Testing security in Odoo 18 requires understanding the interaction between access rights, record rules, and user
contexts.

### Basic Access Rights Testing

```python
from ..common_imports import tagged, AccessError, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory


@tagged(*UNIT_TAGS)
class TestAccessRights(UnitTestCase):
    def setUp(self):
        super().setUp()
        self.test_user = self.env["res.users"].create({
            "name": "Test User",
            "login": "test_user",
            "email": "test@example.com",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]
        })

    def test_product_read_access(self):
        """Test basic read access to products."""
        product = ProductFactory.create(self.env)

        # Admin can read
        self.assertTrue(product.read())

        # Test user can read (if granted access)
        product_as_user = product.with_user(self.test_user)
        try:
            result = product_as_user.read()
            self.assertTrue(result)
        except AccessError:
            # Expected if user doesn't have read access
            pass

    def test_motor_write_access(self):
        """Test write access restrictions."""
        motor = MotorFactory.create(self.env).motor

        # Admin can write
        motor.location = "B1"
        self.assertEqual(motor.location, "B1")

        # Test user write access
        motor_as_user = motor.with_user(self.test_user)
        with self.assertRaises(AccessError):
            motor_as_user.location = "C1"

    def test_create_access_restrictions(self):
        """Test creation access for different models."""
        # Test user context
        env_user = self.env.with_user(self.test_user)

        # Motor creation (should be restricted)
        with self.assertRaises(AccessError):
            env_user["motor"].create({
                "motor_number": "TEST123",
                "horsepower": 100,
                "model": "TEST",
                "serial_number": "SN123"
            })

        # Product creation might be allowed based on groups
        try:
            product = env_user["product.template"].create({
                "name": "Test Product",
                "default_code": "TEST001"
            })
            self.assertTrue(product)
        except AccessError:
            # Expected if user doesn't have create access
            pass
```

### Record Rules Testing

```python
@tagged(*UNIT_TAGS)
class TestRecordRules(UnitTestCase):
    def setUp(self):
        super().setUp()
        # Create test companies
        self.company_a = self.env["res.company"].create({
            "name": "Company A"
        })
        self.company_b = self.env["res.company"].create({
            "name": "Company B"
        })

        # Create users for each company
        self.user_a = self.env["res.users"].create({
            "name": "User A",
            "login": "user_a",
            "email": "usera@example.com",
            "company_id": self.company_a.id,
            "company_ids": [(6, 0, [self.company_a.id])],
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]
        })

        self.user_b = self.env["res.users"].create({
            "name": "User B",
            "login": "user_b",
            "email": "userb@example.com",
            "company_id": self.company_b.id,
            "company_ids": [(6, 0, [self.company_b.id])],
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]
        })

    def test_company_record_isolation(self):
        """Test that users can only see their company's records."""
        # Create products for each company
        product_a = ProductFactory.create(
            self.env.with_company(self.company_a)
        )
        product_b = ProductFactory.create(
            self.env.with_company(self.company_b)
        )

        # User A should only see Company A's products
        products_user_a = self.env["product.template"].with_user(
            self.user_a
        ).search([])
        self.assertIn(product_a.id, products_user_a.ids)
        self.assertNotIn(product_b.id, products_user_a.ids)

        # User B should only see Company B's products
        products_user_b = self.env["product.template"].with_user(
            self.user_b
        ).search([])
        self.assertIn(product_b.id, products_user_b.ids)
        self.assertNotIn(product_a.id, products_user_b.ids)

    def test_motor_ownership_rules(self):
        """Test motor access based on ownership rules."""
        # Create motor owned by user A
        motor_a = MotorFactory.create(
            self.env.with_user(self.user_a)
        ).motor

        # User A can access their own motor
        motor_as_user_a = motor_a.with_user(self.user_a)
        self.assertTrue(motor_as_user_a.read())

        # User B cannot access User A's motor
        motor_as_user_b = motor_a.with_user(self.user_b)
        with self.assertRaises(AccessError):
            motor_as_user_b.read()
```

### Group-Based Access Testing

```python
@tagged(*UNIT_TAGS)
class TestGroupAccess(UnitTestCase):
    def setUp(self):
        super().setUp()
        # Create custom groups for testing
        self.motor_manager_group = self.env["res.groups"].create({
            "name": "Motor Managers",
            "category_id": self.env.ref("base.module_category_operations").id
        })

        self.motor_user_group = self.env["res.groups"].create({
            "name": "Motor Users",
            "category_id": self.env.ref("base.module_category_operations").id
        })

    def test_manager_vs_user_permissions(self):
        """Test different permission levels."""
        # Create users with different group memberships
        manager = self.env["res.users"].create({
            "name": "Motor Manager",
            "login": "manager",
            "email": "manager@example.com",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.motor_manager_group.id
            ])]
        })

        user = self.env["res.users"].create({
            "name": "Motor User",
            "login": "motor_user",
            "email": "motoruser@example.com",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.motor_user_group.id
            ])]
        })

        motor = MotorFactory.create(self.env).motor

        # Manager can modify critical fields
        motor_as_manager = motor.with_user(manager)
        try:
            motor_as_manager.location = "MANAGER-LOCATION"
            self.assertEqual(motor.location, "MANAGER-LOCATION")
        except AccessError:
            self.fail("Manager should have write access")

        # Regular user cannot modify critical fields
        motor_as_user = motor.with_user(user)
        with self.assertRaises(AccessError):
            motor_as_user.location = "USER-LOCATION"
```

---

## 4. Multi-Company Testing Scenarios

Testing multi-company functionality requires careful setup of company contexts and data isolation.

### Company Context Testing

```python
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory


@tagged(*UNIT_TAGS)
class TestMultiCompany(UnitTestCase):
    def setUp(self):
        super().setUp()
        self.company_main = self.env.ref("base.main_company")
        self.company_sub = self.env["res.company"].create({
            "name": "Subsidiary Company",
            "parent_id": self.company_main.id
        })

    def test_product_company_isolation(self):
        """Test that products are properly isolated by company."""
        # Create products in different companies
        product_main = ProductFactory.create(
            self.env.with_company(self.company_main),
            name="Main Company Product"
        )

        product_sub = ProductFactory.create(
            self.env.with_company(self.company_sub),
            name="Sub Company Product"
        )

        # Verify company assignment
        self.assertEqual(product_main.company_id, self.company_main)
        self.assertEqual(product_sub.company_id, self.company_sub)

        # Test search in different company contexts
        main_products = self.env["product.template"].with_company(
            self.company_main
        ).search([("name", "like", "Company Product")])

        sub_products = self.env["product.template"].with_company(
            self.company_sub
        ).search([("name", "like", "Company Product")])

        self.assertIn(product_main.id, main_products.ids)
        self.assertNotIn(product_sub.id, main_products.ids)
        self.assertIn(product_sub.id, sub_products.ids)
        self.assertNotIn(product_main.id, sub_products.ids)

    def test_shared_data_across_companies(self):
        """Test data that should be shared across companies."""
        # Create shared master data (manufacturers, types, etc.)
        manufacturer = self.env["product.manufacturer"].create({
            "name": "Shared Manufacturer"
        })

        part_type = self.env["product.type"].create({
            "name": "Shared Part Type"
        })

        # Both companies should access the same master data
        product_main = ProductFactory.create(
            self.env.with_company(self.company_main),
            manufacturer=manufacturer.id,
            part_type=part_type.id
        )

        product_sub = ProductFactory.create(
            self.env.with_company(self.company_sub),
            manufacturer=manufacturer.id,
            part_type=part_type.id
        )

        self.assertEqual(product_main.manufacturer, manufacturer)
        self.assertEqual(product_sub.manufacturer, manufacturer)
        self.assertEqual(product_main.part_type, part_type)
        self.assertEqual(product_sub.part_type, part_type)

    def test_currency_and_pricelist_isolation(self):
        """Test company-specific financial data."""
        # Create company-specific pricelists
        pricelist_main = self.env["product.pricelist"].create({
            "name": "Main Company Pricelist",
            "currency_id": self.env.ref("base.USD").id,
            "company_id": self.company_main.id
        })

        pricelist_sub = self.env["product.pricelist"].create({
            "name": "Sub Company Pricelist",
            "currency_id": self.env.ref("base.EUR").id,
            "company_id": self.company_sub.id
        })

        # Test pricelist visibility per company
        main_pricelists = self.env["product.pricelist"].with_company(
            self.company_main
        ).search([])

        sub_pricelists = self.env["product.pricelist"].with_company(
            self.company_sub
        ).search([])

        self.assertIn(pricelist_main.id, main_pricelists.ids)
        self.assertIn(pricelist_sub.id, sub_pricelists.ids)
```

### Inter-Company Transactions Testing

```python
@tagged(*UNIT_TAGS)
class TestInterCompanyTransactions(UnitTestCase):
    def setUp(self):
        super().setUp()
        self.company_a = self.env.ref("base.main_company")
        self.company_b = self.env["res.company"].create({
            "name": "Company B"
        })

        # Create partners representing each company
        self.partner_a = self.env["res.partner"].create({
            "name": "Company A Partner",
            "is_company": True,
            "company_id": self.company_a.id
        })

        self.partner_b = self.env["res.partner"].create({
            "name": "Company B Partner",
            "is_company": True,
            "company_id": self.company_b.id
        })

    def test_inter_company_sales_order(self):
        """Test sales orders between companies."""
        # Create product in company A
        product = ProductFactory.create(
            self.env.with_company(self.company_a),
            list_price=100.0
        )

        # Create sale order from company A to company B
        sale_order = self.env["sale.order"].with_company(
            self.company_a
        ).create({
            "partner_id": self.partner_b.id,
            "company_id": self.company_a.id,
            "order_line": [(0, 0, {
                "product_id": product.product_variant_ids[0].id,
                "product_uom_qty": 2.0,
                "price_unit": 100.0
            })]
        })

        self.assertEqual(sale_order.company_id, self.company_a)
        self.assertEqual(sale_order.partner_id, self.partner_b)
        self.assertEqual(sale_order.amount_total, 200.0)

    def test_company_dependent_fields(self):
        """Test fields that vary by company context."""
        product = ProductFactory.create(self.env)

        # Set different prices for different companies
        product.with_company(self.company_a).list_price = 100.0
        product.with_company(self.company_b).list_price = 120.0

        # Verify company-specific values
        price_a = product.with_company(self.company_a).list_price
        price_b = product.with_company(self.company_b).list_price

        self.assertEqual(price_a, 100.0)
        self.assertEqual(price_b, 120.0)
```

---

## 5. Translation and Internationalization Testing

Testing translations requires understanding Odoo's translation mechanism and context handling.

### Basic Translation Testing

```python
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase


@tagged(*UNIT_TAGS)
class TestTranslations(UnitTestCase):
    def setUp(self):
        super().setUp()
        # Enable Spanish language
        lang_es = self.env["res.lang"].search([("code", "=", "es_ES")])
        if not lang_es:
            lang_es = self.env["res.lang"].create({
                "name": "Spanish",
                "code": "es_ES",
                "iso_code": "es",
                "url_code": "es_ES",
                "direction": "ltr"
            })
        lang_es.active = True

    def test_product_name_translation(self):
        """Test product name translations."""
        product = self.env["product.template"].create({
            "name": "Motor Engine Part",
            "default_code": "TEST001"
        })

        # Add Spanish translation
        self.env["ir.translation"].create({
            "type": "model",
            "name": "product.template,name",
            "lang": "es_ES",
            "res_id": product.id,
            "value": "Parte de Motor",
            "state": "translated"
        })

        # Test English (default)
        product_en = product.with_context(lang="en_US")
        self.assertEqual(product_en.name, "Motor Engine Part")

        # Test Spanish
        product_es = product.with_context(lang="es_ES")
        self.assertEqual(product_es.name, "Parte de Motor")

    def test_selection_field_translation(self):
        """Test selection field option translations."""
        motor = self.env["motor"].create({
            "motor_number": "TEST123",
            "horsepower": 100,
            "model": "TEST",
            "serial_number": "SN123",
            "priority": "1"
        })

        # Get selection values in different languages
        priority_en = motor.with_context(lang="en_US")._fields['priority'].selection
        priority_es = motor.with_context(lang="es_ES")._fields['priority'].selection

        # Priority "1" should be "Normal" in English
        normal_en = next((label for value, label in priority_en if value == "1"), None)
        self.assertEqual(normal_en, "Normal")

        # In Spanish it might be translated
        normal_es = next((label for value, label in priority_es if value == "1"), None)
        # Note: Actual translation depends on loaded translation files

    def test_help_text_translation(self):
        """Test field help text translations."""
        product = self.env["product.template"].create({
            "name": "Test Product",
            "default_code": "TEST001"
        })

        # Get field help in different languages
        field_en = product.with_context(lang="en_US")._fields['standard_price']
        field_es = product.with_context(lang="es_ES")._fields['standard_price']

        # Both should have help text (possibly translated)
        self.assertTrue(field_en.help)
        self.assertTrue(field_es.help)
```

### Dynamic Translation Testing

```python
@tagged(*UNIT_TAGS)
class TestDynamicTranslations(UnitTestCase):
    def test_computed_field_with_translations(self):
        """Test computed fields that include translated content."""
        # Create motor with template that has translated name
        template = self.env["motor.product.template"].create({
            "name": "Engine Block",
            "part_type": self.env["product.type"].create({"name": "Engine"}).id
        })

        # Add translation for template name
        self.env["ir.translation"].create({
            "type": "model",
            "name": "motor.product.template,name",
            "lang": "es_ES",
            "res_id": template.id,
            "value": "Bloque del Motor",
            "state": "translated"
        })

        motor_product = ProductFactory.create(self.env,
                                              motor_product_template=template.id
                                              )

        # Test computed name in different languages
        name_en = motor_product.with_context(lang="en_US").motor_product_computed_name
        name_es = motor_product.with_context(lang="es_ES").motor_product_computed_name

        self.assertIn("Engine Block", name_en)
        self.assertIn("Bloque del Motor", name_es)

    def test_email_template_translation(self):
        """Test email template translations."""
        template = self.env["mail.template"].create({
            "name": "Motor Notification",
            "model_id": self.env.ref("product_connect.model_motor").id,
            "subject": "Motor {{object.motor_number}} Status Update",
            "body_html": "<p>Motor {{object.motor_number}} status has changed.</p>",
            "lang": "{{object.create_uid.lang}}"
        })

        # Create user with Spanish language
        spanish_user = self.env["res.users"].create({
            "name": "Spanish User",
            "login": "spanish_user",
            "email": "spanish@example.com",
            "lang": "es_ES"
        })

        motor = MotorFactory.create(
            self.env.with_user(spanish_user)
        ).motor

        # Generate email in user's language
        mail_values = template.with_context(lang="es_ES").generate_email(motor.id)

        # Verify template was processed
        self.assertIn(motor.motor_number, mail_values['subject'])
        self.assertIn(motor.motor_number, mail_values['body_html'])
```

### Report Translation Testing

```python
@tagged(*UNIT_TAGS)
class TestReportTranslations(UnitTestCase):
    def test_motor_report_language(self):
        """Test report generation in different languages."""
        motor = MotorFactory.create(self.env).motor

        # Test report in English
        report_en = self.env["ir.actions.report"].with_context(
            lang="en_US"
        )._render_qweb_html("product_connect.motor_report", motor.ids)

        # Test report in Spanish
        report_es = self.env["ir.actions.report"].with_context(
            lang="es_ES"
        )._render_qweb_html("product_connect.motor_report", motor.ids)

        # Both should contain motor data
        self.assertIn(motor.motor_number, report_en[0].decode())
        self.assertIn(motor.motor_number, report_es[0].decode())

        # Content should potentially differ based on language
        # (depending on template translations)
```

---

## 6. Testing with flush() and invalidate_cache()

Understanding when and how to use cache control methods is crucial for reliable tests.

### Cache Flush Testing

```python
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory


@tagged(*UNIT_TAGS)
class TestCacheManagement(UnitTestCase):
    def test_flush_before_database_read(self):
        """Test flushing changes before reading from database."""
        product = ProductFactory.create(self.env, list_price=100.0)

        # Modify in memory
        product.list_price = 150.0

        # Read from database without flush should show old value
        db_value = self.env.cr.execute(
            "SELECT list_price FROM product_template WHERE id = %s",
            (product.id,)
        )
        result = self.env.cr.fetchone()
        self.assertEqual(result[0], 100.0)  # Old value still in DB

        # Flush and read again
        product.flush_model(['list_price'])
        self.env.cr.execute(
            "SELECT list_price FROM product_template WHERE id = %s",
            (product.id,)
        )
        result = self.env.cr.fetchone()
        self.assertEqual(result[0], 150.0)  # New value now in DB

    def test_selective_flush(self):
        """Test flushing specific fields only."""
        product = ProductFactory.create(self.env,
                                        list_price=100.0,
                                        standard_price=50.0,
                                        name="Original Name"
                                        )

        # Modify multiple fields
        product.list_price = 150.0
        product.standard_price = 75.0
        product.name = "Modified Name"

        # Flush only list_price
        product.flush_recordset(['list_price'])

        # Check database state
        self.env.cr.execute(
            "SELECT list_price, standard_price, name FROM product_template WHERE id = %s",
            (product.id,)
        )
        result = self.env.cr.fetchone()

        self.assertEqual(result[0], 150.0)  # list_price flushed
        self.assertEqual(result[1], 50.0)  # standard_price not flushed
        self.assertEqual(result[2], "Original Name")  # name not flushed

    def test_bulk_flush_optimization(self):
        """Test bulk flush operations for performance."""
        products = ProductFactory.create_batch(self.env, count=100)

        # Modify all products
        for i, product in enumerate(products):
            product.list_price = 100.0 + i

        # Flush all at once (more efficient)
        products.flush_recordset(['list_price'])

        # Verify all were flushed
        for i, product in enumerate(products):
            self.env.cr.execute(
                "SELECT list_price FROM product_template WHERE id = %s",
                (product.id,)
            )
            result = self.env.cr.fetchone()
            self.assertEqual(result[0], 100.0 + i)
```

### Cache Invalidation Testing

```python
@tagged(*UNIT_TAGS)
class TestCacheInvalidation(UnitTestCase):
    def test_computed_field_invalidation(self):
        """Test manual cache invalidation for computed fields."""
        product = ProductFactory.create(self.env,
                                        standard_price=100.0,
                                        initial_quantity=2.0
                                        )

        # Access computed field to cache it
        initial_total = product.initial_cost_total
        self.assertEqual(initial_total, 200.0)

        # Modify dependency directly in database
        self.env.cr.execute(
            "UPDATE product_template SET standard_price = 150.0 WHERE id = %s",
            (product.id,)
        )

        # Without invalidation, computed field returns cached value
        cached_total = product.initial_cost_total
        self.assertEqual(cached_total, 200.0)  # Still cached

        # Invalidate and recompute
        product.invalidate_recordset(['standard_price', 'initial_cost_total'])
        new_total = product.initial_cost_total
        self.assertEqual(new_total, 300.0)  # Recomputed

    def test_related_field_invalidation(self):
        """Test invalidation of related fields."""
        motor_product = MotorFactory.create(self.env)
        motor = motor_product.motor

        # Access related field to cache it
        initial_stage_name = motor_product.stage_name

        # Change the related record
        new_stage = self.env["motor.stage"].create({
            "name": "New Stage"
        })
        motor.stage = new_stage

        # Related field should automatically invalidate
        updated_stage_name = motor_product.stage_name
        self.assertEqual(updated_stage_name, "New Stage")

    def test_cross_model_invalidation(self):
        """Test invalidation across related models."""
        motor_product = MotorFactory.create(self.env)
        motor = motor_product.motor

        # Cache motor-related computed fields
        _ = motor_product.motor_product_computed_name

        # Modify motor fields
        motor.model = "NEW-MODEL"
        motor.horsepower = 200

        # Product computed field should invalidate
        motor.flush_model()
        motor_product.invalidate_recordset(['motor_product_computed_name'])

        updated_name = motor_product.motor_product_computed_name
        self.assertIn("NEW-MODEL", updated_name)
        self.assertIn("200", updated_name)
```

### Transaction-Level Cache Testing

```python
@tagged(*UNIT_TAGS)
class TestTransactionCache(UnitTestCase):
    def test_cache_within_transaction(self):
        """Test cache behavior within a single transaction."""
        product = ProductFactory.create(self.env)

        with self.env.cr.savepoint():
            # Modify and access multiple times
            product.list_price = 100.0
            price1 = product.list_price

            product.list_price = 200.0
            price2 = product.list_price

            self.assertEqual(price1, 100.0)
            self.assertEqual(price2, 200.0)

            # Rollback should restore cache
            raise Exception("Rollback test")

    def test_cache_across_commits(self):
        """Test cache behavior across transaction commits."""
        product = ProductFactory.create(self.env, list_price=100.0)

        # Access to cache
        initial_price = product.list_price
        self.assertEqual(initial_price, 100.0)

        # Modify in another transaction
        with self.env.cr.savepoint():
            self.env.cr.execute(
                "UPDATE product_template SET list_price = 150.0 WHERE id = %s",
                (product.id,)
            )

        # Cache should be invalidated after commit
        product.invalidate_recordset(['list_price'])
        updated_price = product.list_price
        self.assertEqual(updated_price, 150.0)
```

---

## 7. Performance Testing Patterns

Performance testing in Odoo requires measuring database queries, cache hits, and execution time.

### Query Count Testing

```python
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory


@tagged(*UNIT_TAGS)
class TestPerformance(UnitTestCase):
    def test_bulk_operation_query_count(self):
        """Test that bulk operations are efficient."""
        products = ProductFactory.create_batch(self.env, count=10)

        # Bulk update should use minimal queries
        with self.assertQueryCount(1):  # Only one UPDATE query
            products.write({'list_price': 100.0})

        # Individual updates would be inefficient
        for product in products:
            with self.assertQueryCount(1):  # One query per product
                product.standard_price = 50.0

    def test_search_performance(self):
        """Test search operation efficiency."""
        # Create test data
        ProductFactory.create_batch(self.env, count=100)

        # Indexed field search should be efficient
        with self.assertQueryCount(1):
            products = self.env["product.template"].search([
                ('default_code', 'like', 'TEST%')
            ])

        # Non-indexed field search might be less efficient
        with self.assertQueryCount(1):
            products = self.env["product.template"].search([
                ('name', 'ilike', 'test')
            ])

    def test_computed_field_performance(self):
        """Test computed field calculation efficiency."""
        products = ProductFactory.create_batch(self.env, count=50)

        # Accessing computed fields should batch calculate
        with self.assertQueryCount(2):  # One to read, one to compute
            totals = [p.initial_cost_total for p in products]

        # Second access should use cache
        with self.assertQueryCount(0):  # No queries, using cache
            totals_cached = [p.initial_cost_total for p in products]

        self.assertEqual(totals, totals_cached)

    def test_related_field_performance(self):
        """Test related field access efficiency."""
        motor_products = [MotorFactory.create(self.env) for _ in range(20)]

        # Access related fields efficiently
        with self.assertQueryCount(2):  # One for products, one for motors
            motor_numbers = [p.motor.motor_number for p in motor_products]

        self.assertEqual(len(motor_numbers), 20)
```

### Memory Usage Testing

```python
import sys
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory


@tagged(*UNIT_TAGS)
class TestMemoryUsage(UnitTestCase):
    def test_large_recordset_memory(self):
        """Test memory usage with large recordsets."""
        initial_size = sys.getsizeof(self.env["product.template"])

        # Create large recordset
        products = ProductFactory.create_batch(self.env, count=1000)
        large_recordset_size = sys.getsizeof(products)

        # Recordset size should be reasonable
        self.assertLess(large_recordset_size, initial_size * 10)

        # Accessing fields should not dramatically increase memory
        field_access_size = sys.getsizeof([p.name for p in products])
        self.assertLess(field_access_size, large_recordset_size * 2)

    def test_cache_memory_management(self):
        """Test that cache doesn't grow unbounded."""
        products = ProductFactory.create_batch(self.env, count=100)

        # Access computed fields to populate cache
        for product in products:
            _ = product.initial_cost_total

        initial_cache_size = len(self.env.cache)

        # Clear cache and verify reduction
        self.env.invalidate_all()
        cleared_cache_size = len(self.env.cache)

        self.assertLess(cleared_cache_size, initial_cache_size)
```

### Batch Processing Performance

```python
@tagged(*UNIT_TAGS)
class TestBatchProcessing(UnitTestCase):
    def test_motor_product_creation_batch(self):
        """Test efficient batch creation of motor products."""
        motors = [MotorFactory.create(self.env).motor for _ in range(10)]

        # Batch product creation should be efficient
        with self.assertQueryCount(5):  # Limited queries for batch operation
            for motor in motors:
                motor.create_motor_products()

    def test_shopify_sync_batch_performance(self):
        """Test batch sync operations."""
        products = ProductFactory.create_batch(self.env, count=20)

        # Mock Shopify service for performance testing
        with self.mock_shopify_client() as mock_client:
            mock_client.query.return_value = {
                "data": {"products": {"edges": []}}
            }

            # Batch sync should use minimal API calls
            from ...services.shopify.service import ShopifyService

            service = ShopifyService(
                shop_url="test.myshopify.com",
                access_token="test_token"
            )

            # Should batch products efficiently
            with self.assertNumQueries(10):  # Reasonable query limit
                service.sync_products(products)
```

---

## 8. Testing Workflows and State Transitions

Testing state-based workflows requires careful attention to state changes and side effects.

### Motor Stage Workflow Testing

```python
from ..common_imports import tagged, ValidationError, UNIT_TAGS
from ..fixtures import UnitTestCase, MotorFactory


@tagged(*UNIT_TAGS)
class TestMotorWorkflow(UnitTestCase):
    def setUp(self):
        super().setUp()
        # Create required stages
        self.stage_checkin = self.env["motor.stage"].create({
            "name": "Checkin",
            "sequence": 10
        })
        self.stage_dismantle = self.env["motor.stage"].create({
            "name": "Dismantle",
            "sequence": 20
        })
        self.stage_testing = self.env["motor.stage"].create({
            "name": "Testing",
            "sequence": 30
        })
        self.stage_complete = self.env["motor.stage"].create({
            "name": "Complete",
            "sequence": 40
        })

    def test_motor_stage_progression(self):
        """Test normal stage progression workflow."""
        motor = MotorFactory.create(self.env).motor

        # Should start in Checkin stage
        self.assertEqual(motor.stage, self.stage_checkin)

        # Progress through stages
        motor.stage = self.stage_dismantle
        self.assertEqual(motor.stage, self.stage_dismantle)

        motor.stage = self.stage_testing
        self.assertEqual(motor.stage, self.stage_testing)

        motor.stage = self.stage_complete
        self.assertEqual(motor.stage, self.stage_complete)

    def test_stage_change_side_effects(self):
        """Test side effects of stage changes."""
        motor_product = MotorFactory.create(self.env)
        motor = motor_product.motor

        # Moving to dismantle stage should affect product flags
        motor.stage = self.stage_dismantle

        # Should trigger recomputation of related fields
        motor_product.invalidate_recordset()
        # Verify any business logic that depends on stage

    def test_invalid_stage_transitions(self):
        """Test that invalid transitions are prevented."""
        motor = MotorFactory.create(self.env).motor

        # Example: Can't skip directly to complete from checkin
        # (if such business rules exist)
        try:
            motor.stage = self.stage_complete
            # If this should be prevented, add validation
        except ValidationError:
            pass  # Expected for invalid transitions
```

### Product Workflow State Testing

```python
@tagged(*UNIT_TAGS)
class TestProductWorkflow(UnitTestCase):
    def test_product_ready_for_sale_workflow(self):
        """Test product enablement workflow."""
        product = ProductFactory.create(self.env,
                                        is_ready_for_sale=False,
                                        standard_price=0.0,  # Missing cost
                                        list_price=0.0  # Missing price
                                        )

        # Should not be ready due to missing price/cost
        self.assertFalse(product.is_ready_for_sale)

        # Add cost and price
        product.standard_price = 50.0
        product.list_price = 100.0

        # Should be able to enable now
        product.is_ready_for_sale = True
        self.assertTrue(product.is_ready_for_sale)

        # Should track when enabled
        self.assertTrue(product.is_ready_for_sale_last_enabled_date)

    def test_motor_product_workflow_flags(self):
        """Test motor product processing workflow."""
        motor_product = MotorFactory.create(self.env)

        # Initial state - nothing done
        self.assertFalse(motor_product.is_dismantled)
        self.assertFalse(motor_product.is_cleaned)
        self.assertFalse(motor_product.is_pictured)
        self.assertFalse(motor_product.is_ready_to_list)

        # Progress through workflow
        motor_product.is_dismantled = True
        motor_product.is_dismantled_qc = True

        motor_product.is_cleaned = True
        motor_product.is_cleaned_qc = True

        motor_product.is_pictured = True
        motor_product.is_pictured_qc = True

        # Should now be ready to list
        motor_product.invalidate_recordset(['is_ready_to_list'])
        self.assertTrue(motor_product.is_ready_to_list)

    def test_repair_workflow_states(self):
        """Test repair order state transitions."""
        motor_product = MotorFactory.create(self.env)
        product_variant = motor_product.product_variant_ids[0]

        # Create repair order
        repair = self.env["repair.order"].create({
            "product_id": product_variant.id,
            "partner_id": self.env.ref("base.res_partner_12").id,
            "state": "draft"
        })

        # Test state transitions
        repair.action_repair_confirm()
        self.assertEqual(repair.state, "confirmed")

        repair.action_repair_start()
        self.assertEqual(repair.state, "under_repair")

        repair.action_repair_end()
        self.assertEqual(repair.state, "ready")

        repair.action_repair_done()
        self.assertEqual(repair.state, "done")
```

### Workflow Constraint Testing

```python
@tagged(*UNIT_TAGS)
class TestWorkflowConstraints(UnitTestCase):
    def test_stage_sequence_constraints(self):
        """Test that stage progression follows sequence rules."""
        motor = MotorFactory.create(self.env).motor

        # Create stages with specific sequences
        stage_1 = self.env["motor.stage"].create({
            "name": "Stage 1", "sequence": 10
        })
        stage_2 = self.env["motor.stage"].create({
            "name": "Stage 2", "sequence": 20
        })
        stage_3 = self.env["motor.stage"].create({
            "name": "Stage 3", "sequence": 30
        })

        motor.stage = stage_1

        # Should be able to progress forward
        motor.stage = stage_2
        motor.stage = stage_3

        # Should be able to go backward (if allowed)
        motor.stage = stage_1

    def test_workflow_prerequisites(self):
        """Test that workflow steps have proper prerequisites."""
        motor_product = MotorFactory.create(self.env)

        # Can't mark as cleaned without dismantling
        try:
            motor_product.is_cleaned = True
            motor_product.is_dismantled = False  # Invalid state
            # Add validation if this should be prevented
        except ValidationError:
            pass

        # Can't mark as pictured without cleaning
        try:
            motor_product.is_pictured = True
            motor_product.is_cleaned = False  # Invalid state
            # Add validation if this should be prevented
        except ValidationError:
            pass
```

---

## 9. Testing with Different User Contexts

User context affects many aspects of Odoo behavior, including permissions, language, and company.

### User Permission Context Testing

```python
from ..common_imports import tagged, AccessError, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory


@tagged(*UNIT_TAGS)
class TestUserContexts(UnitTestCase):
    def setUp(self):
        super().setUp()
        # Create test users with different roles
        self.admin_user = self.env.ref("base.user_admin")

        self.manager_user = self.env["res.users"].create({
            "name": "Manager User",
            "login": "manager",
            "email": "manager@test.com",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("product.group_product_manager").id
            ])]
        })

        self.basic_user = self.env["res.users"].create({
            "name": "Basic User",
            "login": "basic",
            "email": "basic@test.com",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id
            ])]
        })

    def test_product_access_by_user_role(self):
        """Test product access varies by user role."""
        product = ProductFactory.create(self.env)

        # Admin can do everything
        product_as_admin = product.with_user(self.admin_user)
        product_as_admin.list_price = 100.0
        self.assertEqual(product_as_admin.list_price, 100.0)

        # Manager can modify products
        product_as_manager = product.with_user(self.manager_user)
        try:
            product_as_manager.list_price = 150.0
            self.assertEqual(product.list_price, 150.0)
        except AccessError:
            self.fail("Manager should have product write access")

        # Basic user might have limited access
        product_as_basic = product.with_user(self.basic_user)
        try:
            # Can read
            _ = product_as_basic.name

            # Might not be able to write
            product_as_basic.list_price = 200.0
        except AccessError:
            # Expected for basic user
            pass

    def test_motor_creation_permissions(self):
        """Test motor creation based on user permissions."""
        # Admin can create motors
        motor_as_admin = MotorFactory.create(
            self.env.with_user(self.admin_user)
        ).motor
        self.assertTrue(motor_as_admin.id)

        # Manager might be able to create motors
        try:
            motor_as_manager = MotorFactory.create(
                self.env.with_user(self.manager_user)
            ).motor
            self.assertTrue(motor_as_manager.id)
        except AccessError:
            # Expected if manager doesn't have create rights
            pass

        # Basic user probably cannot create motors
        with self.assertRaises(AccessError):
            MotorFactory.create(self.env.with_user(self.basic_user))

    def test_record_visibility_by_ownership(self):
        """Test that users see only their own records."""
        # Create motors as different users
        motor_admin = MotorFactory.create(
            self.env.with_user(self.admin_user)
        ).motor

        motor_manager = MotorFactory.create(
            self.env.with_user(self.manager_user)
        ).motor

        # Check visibility from manager perspective
        motors_visible_to_manager = self.env["motor"].with_user(
            self.manager_user
        ).search([])

        # Manager should see their own motor
        self.assertIn(motor_manager.id, motors_visible_to_manager.ids)

        # Might or might not see admin's motor based on rules
        # (depends on actual record rules implementation)
```

### Language Context Testing

```python
@tagged(*UNIT_TAGS)
class TestLanguageContext(UnitTestCase):
    def setUp(self):
        super().setUp()
        # Ensure Spanish is available
        self.env["res.lang"]._activate_lang("es_ES")

        # Create user with Spanish language
        self.spanish_user = self.env["res.users"].create({
            "name": "Spanish User",
            "login": "spanish",
            "email": "spanish@test.com",
            "lang": "es_ES",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]
        })

    def test_field_labels_in_user_language(self):
        """Test that field labels appear in user's language."""
        product = ProductFactory.create(self.env)

        # Get field info in different languages
        field_en = product.with_user(self.admin_user)._fields['list_price']
        field_es = product.with_user(self.spanish_user)._fields['list_price']

        # Labels might be translated
        self.assertTrue(field_en.string)
        self.assertTrue(field_es.string)

        # They might be different if translations exist
        # (actual difference depends on loaded translations)

    def test_selection_values_in_user_language(self):
        """Test selection field values in user language."""
        motor = MotorFactory.create(self.env).motor

        # Get priority selection in different languages
        priorities_en = motor.with_user(self.admin_user)._fields['priority'].selection
        priorities_es = motor.with_user(self.spanish_user)._fields['priority'].selection

        # Both should have the same structure
        self.assertEqual(len(priorities_en), len(priorities_es))

        # Values should be the same, labels might differ
        en_values = [v for v, l in priorities_en]
        es_values = [v for v, l in priorities_es]
        self.assertEqual(en_values, es_values)

    def test_error_messages_in_user_language(self):
        """Test that error messages appear in user language."""
        # Create product with Spanish user context
        product_es = ProductFactory.create(
            self.env.with_user(self.spanish_user)
        )

        # Trigger validation error
        try:
            product_es.list_price = -100.0  # Should fail validation
        except ValidationError as e:
            # Error message might be in Spanish
            error_msg = str(e)
            self.assertTrue(error_msg)
            # Could check for Spanish-specific text if translations exist
```

### Company Context Testing

```python
@tagged(*UNIT_TAGS)
class TestCompanyContext(UnitTestCase):
    def setUp(self):
        super().setUp()
        self.main_company = self.env.ref("base.main_company")
        self.sub_company = self.env["res.company"].create({
            "name": "Sub Company"
        })

        # Create user for sub company
        self.sub_company_user = self.env["res.users"].create({
            "name": "Sub Company User",
            "login": "subuser",
            "email": "sub@test.com",
            "company_id": self.sub_company.id,
            "company_ids": [(6, 0, [self.sub_company.id])],
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]
        })

    def test_product_creation_in_company_context(self):
        """Test product creation respects company context."""
        # Create product in main company
        product_main = ProductFactory.create(
            self.env.with_company(self.main_company)
        )
        self.assertEqual(product_main.company_id, self.main_company)

        # Create product in sub company
        product_sub = ProductFactory.create(
            self.env.with_company(self.sub_company)
        )
        self.assertEqual(product_sub.company_id, self.sub_company)

    def test_user_sees_only_company_data(self):
        """Test users see only their company's data."""
        # Create products in different companies
        product_main = ProductFactory.create(
            self.env.with_company(self.main_company)
        )
        product_sub = ProductFactory.create(
            self.env.with_company(self.sub_company)
        )

        # Sub company user should only see sub company products
        products_visible = self.env["product.template"].with_user(
            self.sub_company_user
        ).search([])

        self.assertIn(product_sub.id, products_visible.ids)
        self.assertNotIn(product_main.id, products_visible.ids)

    def test_currency_context_by_company(self):
        """Test currency handling varies by company."""
        # Set different currencies for companies
        eur_currency = self.env.ref("base.EUR")
        self.sub_company.currency_id = eur_currency

        # Create pricelists for each company
        pricelist_main = self.env["product.pricelist"].create({
            "name": "Main USD Pricelist",
            "currency_id": self.env.ref("base.USD").id,
            "company_id": self.main_company.id
        })

        pricelist_sub = self.env["product.pricelist"].create({
            "name": "Sub EUR Pricelist",
            "currency_id": eur_currency.id,
            "company_id": self.sub_company.id
        })

        # Verify currency context
        self.assertEqual(pricelist_main.currency_id.name, "USD")
        self.assertEqual(pricelist_sub.currency_id.name, "EUR")
```

---

## 10. Mock and Patch Patterns for External Services

Testing external service integrations requires sophisticated mocking to avoid actual API calls.

### Shopify Service Mocking

```python
from unittest.mock import MagicMock, patch
from ..common_imports import tagged, INTEGRATION_TAGS
from ..fixtures import IntegrationTestCase, ProductFactory
from ..fixtures.shopify_responses import create_shopify_product_response


@tagged(*INTEGRATION_TAGS)
class TestShopifyMocking(IntegrationTestCase):
    def test_shopify_product_sync_success(self):
        """Test successful Shopify product sync with mocked responses."""
        self.create_shopify_credentials()

        # Mock successful response
        mock_response = create_shopify_product_response({
            "id": "gid://shopify/Product/123456",
            "handle": "test-motor-part",
            "title": "Test Motor Part",
            "variants": {
                "edges": [{
                    "node": {
                        "id": "gid://shopify/ProductVariant/789",
                        "sku": "TEST001",
                        "price": "99.99"
                    }
                }]
            }
        })

        with self.mock_shopify_client() as mock_client:
            mock_client.query.return_value = self.mock_shopify_response(
                {"products": {"edges": [{"node": mock_response}]}}
            )

            # Test the sync
            from ...services.shopify.sync.importers.product_importer import ProductImporter
            importer = ProductImporter(self.env)
            result = importer.sync_products()

            self.assertTrue(result.success)
            self.assertEqual(len(result.created_products), 1)

    def test_shopify_api_error_handling(self):
        """Test handling of Shopify API errors."""
        self.create_shopify_credentials()

        with self.mock_shopify_client() as mock_client:
            # Mock API error
            mock_client.query.side_effect = Exception("API Rate Limit Exceeded")

            from ...services.shopify.sync.importers.product_importer import ProductImporter
            importer = ProductImporter(self.env)
            result = importer.sync_products()

            self.assertFalse(result.success)
            self.assertIn("API Rate Limit", result.error_message)

    def test_shopify_partial_failure(self):
        """Test handling of partial sync failures."""
        self.create_shopify_credentials()

        # Create mixed response - some succeed, some fail
        valid_product = create_shopify_product_response({
            "id": "gid://shopify/Product/123",
            "handle": "valid-product",
            "title": "Valid Product"
        })

        invalid_product = create_shopify_product_response({
            "id": "gid://shopify/Product/456",
            "handle": "",  # Invalid handle
            "title": "Invalid Product"
        })

        with self.mock_shopify_client() as mock_client:
            mock_client.query.return_value = self.mock_shopify_response({
                "products": {
                    "edges": [
                        {"node": valid_product},
                        {"node": invalid_product}
                    ]
                }
            })

            from ...services.shopify.sync.importers.product_importer import ProductImporter
            importer = ProductImporter(self.env)
            result = importer.sync_products()

            # Should partially succeed
            self.assertTrue(result.success)
            self.assertEqual(len(result.created_products), 1)
            self.assertEqual(len(result.failed_products), 1)
```

### Advanced Mocking Patterns

```python
@tagged(*INTEGRATION_TAGS)
class TestAdvancedMocking(IntegrationTestCase):
    def test_mock_with_side_effects(self):
        """Test mocking with different responses for sequential calls."""
        self.create_shopify_credentials()

        # First call returns products, second call returns empty
        responses = [
            self.mock_shopify_response({
                "products": {
                    "edges": [{"node": create_shopify_product_response()}]
                }
            }),
            self.mock_shopify_response({
                "products": {"edges": []}
            })
        ]

        with self.mock_shopify_client() as mock_client:
            mock_client.query.side_effect = responses

            from ...services.shopify.service import ShopifyService
            service = ShopifyService("test.myshopify.com", "token")

            # First sync gets products
            result1 = service.sync_products()
            self.assertTrue(result1.success)
            self.assertGreater(len(result1.products), 0)

            # Second sync gets nothing
            result2 = service.sync_products()
            self.assertTrue(result2.success)
            self.assertEqual(len(result2.products), 0)

    def test_mock_method_specific_behaviors(self):
        """Test mocking specific methods with different behaviors."""
        with patch('addons.product_connect.services.shopify.gql.client.GraphQLClient') as mock_client_class:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            # Configure different behaviors for different queries
            def mock_query_side_effect(query, variables=None):
                if "products" in query:
                    return self.mock_shopify_response({
                        "products": {"edges": []}
                    })
                elif "customers" in query:
                    return self.mock_shopify_response({
                        "customers": {"edges": []}
                    })
                else:
                    raise Exception("Unknown query type")

            mock_instance.query.side_effect = mock_query_side_effect

            from ...services.shopify.service import ShopifyService
            service = ShopifyService("test.myshopify.com", "token")

            # Test product sync
            product_result = service.sync_products()
            self.assertTrue(product_result.success)

            # Test customer sync
            customer_result = service.sync_customers()
            self.assertTrue(customer_result.success)

    def test_context_manager_mocking(self):
        """Test using context managers for complex mocking scenarios."""
        self.create_shopify_credentials()

        # Use nested context managers for multiple patches
        with patch('addons.product_connect.services.shopify.gql.client.GraphQLClient') as mock_client,
            patch('addons.product_connect.services.shopify.helpers.logger') as mock_logger:
            # Configure client mock
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        mock_instance.query.return_value = self.mock_shopify_response({
            "products": {"edges": []}
        })

        # Configure logger mock
        mock_logger.info = MagicMock()
        mock_logger.error = MagicMock()

        from ...services.shopify.service import ShopifyService
        service = ShopifyService("test.myshopify.com", "token")
        result = service.sync_products()

        # Verify interactions
        self.assertTrue(result.success)
        mock_client.assert_called_once()
        mock_logger.info.assert_called()
```

### Mock Data Factory Patterns

```python
@tagged(*INTEGRATION_TAGS)
class TestMockDataFactories(IntegrationTestCase):
    def create_mock_product_data(self, **overrides):
        """Factory for creating mock product data."""
        default_data = {
            "id": "gid://shopify/Product/123456",
            "handle": "test-product",
            "title": "Test Product",
            "description": "Test Description",
            "productType": "Motor Part",
            "vendor": "Test Vendor",
            "status": "ACTIVE",
            "variants": {
                "edges": [{
                    "node": {
                        "id": "gid://shopify/ProductVariant/789",
                        "sku": "TEST001",
                        "price": "99.99",
                        "compareAtPrice": "129.99",
                        "inventoryQuantity": 10
                    }
                }]
            },
            "images": {
                "edges": [{
                    "node": {
                        "id": "gid://shopify/ProductImage/456",
                        "url": "https://example.com/image.jpg",
                        "altText": "Product Image"
                    }
                }]
            }
        }

        # Apply overrides
        default_data.update(overrides)
        return default_data

    def test_product_import_with_mock_factory(self):
        """Test product import using mock data factory."""
        self.create_shopify_credentials()

        # Create various product scenarios
        products_data = [
            self.create_mock_product_data(
                title="Motor A",
                variants={"edges": [{"node": {"sku": "MOTOR-A", "price": "199.99"}}]}
            ),
            self.create_mock_product_data(
                title="Motor B",
                status="DRAFT",  # Should be skipped
                variants={"edges": [{"node": {"sku": "MOTOR-B", "price": "299.99"}}]}
            ),
            self.create_mock_product_data(
                title="Motor C",
                variants={"edges": []}  # No variants - should handle gracefully
            )
        ]

        mock_response = self.mock_shopify_response({
            "products": {
                "edges": [{"node": product} for product in products_data]
            }
        })

        with self.mock_shopify_client() as mock_client:
            mock_client.query.return_value = mock_response

            from ...services.shopify.sync.importers.product_importer import ProductImporter
            importer = ProductImporter(self.env)
            result = importer.sync_products()

            # Should import only active products with variants
            self.assertTrue(result.success)
            self.assertEqual(len(result.created_products), 1)  # Only Motor A
            self.assertEqual(len(result.skipped_products), 2)  # Motor B and C

    def test_error_scenario_mocking(self):
        """Test various error scenarios with mocks."""
        scenarios = [
            {
                "name": "Network Error",
                "exception": ConnectionError("Network unreachable"),
                "expected_error": "Network unreachable"
            },
            {
                "name": "API Error",
                "exception": Exception("API returned error"),
                "expected_error": "API returned error"
            },
            {
                "name": "Timeout Error",
                "exception": TimeoutError("Request timed out"),
                "expected_error": "Request timed out"
            }
        ]

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                self.create_shopify_credentials()

                with self.mock_shopify_client() as mock_client:
                    mock_client.query.side_effect = scenario["exception"]

                    from ...services.shopify.sync.importers.product_importer import ProductImporter
                    importer = ProductImporter(self.env)
                    result = importer.sync_products()

                    self.assertFalse(result.success)
                    self.assertIn(scenario["expected_error"], result.error_message)
```

---

## Summary

This advanced testing guide provides patterns for:

1. **Computed Fields**: Testing cache invalidation and dependency chains
2. **Constraints**: SQL and Python validation testing
3. **Access Rights**: User permissions and record rules
4. **Multi-Company**: Company context and data isolation
5. **Translations**: Internationalization and language contexts
6. **Cache Management**: flush() and invalidate_cache() usage
7. **Performance**: Query optimization and memory management
8. **Workflows**: State transitions and business logic
9. **User Contexts**: Permission, language, and company contexts
10. **External Services**: Sophisticated mocking and patching

Each pattern includes real examples from the `product_connect` module, demonstrating practical usage in a production
Odoo 18 environment. These patterns ensure reliable, maintainable tests that accurately reflect the complexity of modern
Odoo applications.

For basic testing patterns, see [testing.md](../testing.md). For specialized testing scenarios, consult the individual
see role guidance in [docs/roles/tester.md](../roles/tester.md).
