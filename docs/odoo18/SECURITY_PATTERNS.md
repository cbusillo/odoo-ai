# Odoo 18 Security Patterns

## Overview

This document outlines critical security patterns, best practices, and common pitfalls when implementing security in Odoo 18 applications. Examples are drawn from the product_connect module.

## Table of Contents

- [Access Rights & Record Rules](#access-rights--record-rules)
- [Multi-Company Security](#multi-company-security)
- [Sudo Usage & Security Risks](#sudo-usage--security-risks)
- [Group-Based Access Control](#group-based-access-control)
- [Field-Level Security](#field-level-security)
- [API Security](#api-security)
- [Common Security Pitfalls](#common-security-pitfalls)

## Access Rights & Record Rules

### Access Rights CSV Structure

Access rights are defined in `security/ir.model.access.csv`. Each line defines CRUD permissions for a model/group combination.

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_motor,access_motor,model_motor,base.group_user,1,1,1,0
access_motor_stage_inventory_admin,access_motor_stage_inventory_admin,model_motor_stage,stock.group_stock_manager,1,1,1,1
access_motor_stage_inventory_user,access_motor_stage_inventory_user,model_motor_stage,base.group_user,1,0,0,0
```

### Key Patterns from product_connect

**1. Differentiated Access by Role**
```csv
# Admins get full access
access_motor_stage_inventory_admin,access_motor_stage_inventory_admin,model_motor_stage,stock.group_stock_manager,1,1,1,1
# Users get read-only access
access_motor_stage_inventory_user,access_motor_stage_inventory_user,model_motor_stage,base.group_user,1,0,0,0
```

**2. Prevent Deletion for Critical Data**
```csv
# Motors can be created/updated but not deleted by regular users
access_motor,access_motor,model_motor,base.group_user,1,1,1,0
# Product types and conditions are read-only for data integrity
access_product_type,model_product_type,model_product_type,base.group_user,1,1,1,0
access_product_condition,product.condition,model_product_condition,base.group_user,1,1,1,0
```

**3. Restricted Administrative Access**
```csv
# Shopify sync jobs have restricted write access for regular users
access_shopify_sync_user,access.shopify_sync.user,model_shopify_sync,base.group_user,1,0,0,0
```

### Record Rules Implementation

Record rules provide row-level security. Define them in XML data files:

```xml
<record id="motor_company_rule" model="ir.rule">
    <field name="name">Motor: Company Rule</field>
    <field name="model_id" ref="model_motor"/>
    <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    <field name="groups" eval="[(4, ref('base.group_user'))]"/>
</record>
```

**Best Practices:**
- Always specify `company_id` filtering for multi-company setups
- Use `company_ids` context variable, not hardcoded IDs
- Test record rules with different user contexts

## Multi-Company Security

### Company Isolation Patterns

**1. Model-Level Company Fields**
```python
class Motor(models.Model):
    _name = "motor"
    _check_company_auto = True  # Enables automatic company consistency checks
    
    company_id = fields.Many2one(
        'res.company', 
        required=True, 
        default=lambda self: self.env.company,
        index=True
    )
```

**2. Related Model Consistency**
```python
class MotorPart(models.Model):
    _name = "motor.part"
    _check_company_auto = True
    
    motor_id = fields.Many2one('motor', required=True, check_company=True)
    company_id = fields.Many2one(related='motor_id.company_id', store=True)
```

**3. Multi-Company Search Domains**
```python
# Always filter by allowed companies
def _get_motors_domain(self):
    return [('company_id', 'in', self.env.companies.ids)]

# Use in searches
motors = self.env['motor'].search(self._get_motors_domain())
```

### Company Context Management

```python
# Switch company context safely
motor = self.env['motor'].with_company(target_company_id).create(vals)

# Batch operations across companies
for company in self.env.companies:
    company_motors = self.with_company(company).search([])
    # Process company-specific motors
```

## Sudo Usage & Security Risks

### Safe Sudo Patterns from product_connect

**1. Configuration Parameter Access (Safe)**
```python
# Reading system configuration - typically safe
shop_url_key = self.env["ir.config_parameter"].sudo().get_param("shopify.shop_url_key")
api_key = self.env["ir.config_parameter"].sudo().get_param("printnode.api_key")
```

**2. System User Operations (Safe)**
```python
# Finding system users for automated processes
shopify_user = http.request.env["res.users"].sudo().search([("login", "=", self.SHOPIFY_LOGIN)], limit=1)
```

**3. Cross-Model Access with Controlled Context (Safe)**
```python
# Accessing inactive records for business logic
existing_product = self.env["product.template"].sudo().with_context(active_test=False).search([("default_code", "=", new_sku)], limit=1)
```

**4. Background Job Execution (Controlled Risk)**
```python
# Thread environment with sudo for async operations
sync_jobs = thread_env["shopify.sync"].sudo().browse(self.ids)
# Risk: Bypasses all security, ensure proper input validation
```

### Dangerous Sudo Anti-Patterns

**❌ Never do this:**
```python
# DANGEROUS: Bypasses all security for user input
def create_product(self, vals):
    return self.env['product.template'].sudo().create(vals)  # User could create anything!

# DANGEROUS: Mass operations without validation
def delete_all_motors(self):
    self.env['motor'].sudo().search([]).unlink()  # Deletes everything!

# DANGEROUS: Exposing sensitive data
def get_all_partners(self):
    return self.env['res.partner'].sudo().search([])  # Exposes all customer data
```

**✅ Safe alternatives:**
```python
# SAFE: Validate and limit scope
def create_product(self, vals):
    # Validate user permissions first
    if not self.env.user.has_group('product.group_product_manager'):
        raise AccessError("Insufficient permissions")
    
    # Validate input data
    allowed_fields = ['name', 'description', 'price']
    vals = {k: v for k, v in vals.items() if k in allowed_fields}
    
    return self.env['product.template'].create(vals)
```

### Sudo Best Practices

1. **Minimal Scope**: Use sudo() only for the specific operation needed
2. **Input Validation**: Always validate data before sudo() operations
3. **Permission Checks**: Check user permissions before using sudo()
4. **Documentation**: Document why sudo() is necessary
5. **Audit Trail**: Log sudo() operations for sensitive actions

```python
def safe_sudo_operation(self, vals):
    """Safely perform privileged operation with proper checks."""
    # 1. Validate user permissions
    if not self.env.user.has_group('required.group'):
        raise AccessError("Insufficient permissions")
    
    # 2. Validate input data
    if 'dangerous_field' in vals:
        raise ValidationError("Field not allowed")
    
    # 3. Log the operation
    _logger.info(f"User {self.env.user.login} performing sudo operation: {vals}")
    
    # 4. Minimal sudo scope
    return self.sudo().create(vals)
```

## Group-Based Access Control

### Standard Odoo Groups

```python
# Check user groups in code
if self.env.user.has_group('base.group_user'):
    # Basic user operations
    pass

if self.env.user.has_group('stock.group_stock_manager'):
    # Inventory management operations
    pass

if self.env.user.has_group('sales_team.group_sale_manager'):
    # Sales management operations
    pass
```

### Custom Group Definitions

```xml
<record id="group_motor_technician" model="res.groups">
    <field name="name">Motor Technician</field>
    <field name="category_id" ref="base.module_category_operations"/>
    <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
</record>
```

### Group-Based Field Security

```python
class Motor(models.Model):
    _name = "motor"
    
    # Sensitive field only visible to managers
    internal_notes = fields.Text(
        groups="stock.group_stock_manager"
    )
    
    # Cost information restricted to accounting
    cost_price = fields.Float(
        groups="account.group_account_user"
    )
```

### Method-Level Group Security

```python
class Motor(models.Model):
    _name = "motor"
    
    @api.model
    def sensitive_operation(self):
        """Only managers can perform this operation."""
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError("Only inventory managers can perform this operation")
        
        # Perform sensitive operation
        pass
```

## Field-Level Security

### Field Groups

Control field visibility based on user groups:

```python
class ProductTemplate(models.Model):
    _inherit = "product.template"
    
    # Only accounting users see cost fields
    standard_price = fields.Float(groups="account.group_account_user")
    
    # Only managers see profit margins
    profit_margin = fields.Float(groups="sales_team.group_sale_manager")
    
    # Public information visible to all users
    public_description = fields.Html()
```

### Computed Field Security

```python
class Motor(models.Model):
    _name = "motor"
    
    @api.depends("horsepower")
    def _compute_power_rating(self):
        """Computed field respects group security."""
        for motor in self:
            if self.env.user.has_group('technical.group_engineer'):
                motor.power_rating = motor.horsepower * 0.746  # Convert to kW
            else:
                motor.power_rating = 0  # Hide technical details
```

### Dynamic Field Security

```python
@api.model
def fields_get(self, allfields=None, attributes=None):
    """Override to dynamically control field access."""
    result = super().fields_get(allfields, attributes)
    
    # Hide sensitive fields from non-managers
    if not self.env.user.has_group('stock.group_stock_manager'):
        if 'internal_cost' in result:
            del result['internal_cost']
    
    return result
```

## API Security

### Controller Security

```python
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

class MotorAPI(http.Controller):
    
    @http.route('/api/motors', auth='user', type='json', methods=['GET'])
    def get_motors(self):
        """Secure API endpoint with user authentication."""
        # Authentication handled by auth='user'
        # Additional permission check
        if not request.env.user.has_group('base.group_user'):
            raise AccessError("Insufficient permissions")
        
        # Filter by user's companies
        domain = [('company_id', 'in', request.env.companies.ids)]
        motors = request.env['motor'].search(domain)
        
        return {
            'motors': motors.read(['name', 'motor_number', 'horsepower'])
        }
    
    @http.route('/api/webhooks/shopify', auth='none', type='json', methods=['POST'], csrf=False)
    def shopify_webhook(self):
        """Webhook with custom authentication."""
        # Custom authentication for webhooks
        secret = request.env["ir.config_parameter"].sudo().get_param("shopify.webhook_key")
        provided_secret = request.httprequest.headers.get('X-Shopify-Hmac-Sha256')
        
        if not self._verify_webhook_signature(provided_secret, secret):
            raise AccessError("Invalid webhook signature")
        
        # Process webhook with system user
        shopify_user = request.env["res.users"].sudo().search([("login", "=", "shopify_system")], limit=1)
        if not shopify_user:
            raise ValidationError("Shopify system user not found")
        
        # Execute with controlled context
        return request.env['shopify.sync'].with_user(shopify_user).process_webhook(request.jsonrequest)
```

### GraphQL/REST Security

```python
def _verify_api_access(self, model_name, operation):
    """Verify API access for external integrations."""
    # Check if user has API access
    if not self.env.user.has_group('base.group_system'):
        # Limited API access for external users
        allowed_models = ['product.template', 'res.partner']
        if model_name not in allowed_models:
            raise AccessError(f"API access denied for model {model_name}")
        
        # Read-only access for non-system users
        if operation in ['create', 'write', 'unlink']:
            raise AccessError("Write operations not allowed")
    
    return True
```

## Common Security Pitfalls

### 1. Overprivileged Sudo Usage

**❌ Problem:**
```python
def process_user_data(self, data):
    # DANGEROUS: Processes user input with sudo
    return self.env['sensitive.model'].sudo().create(data)
```

**✅ Solution:**
```python
def process_user_data(self, data):
    # Validate permissions and input first
    self._validate_user_permissions()
    validated_data = self._validate_input_data(data)
    
    # Use regular permissions, not sudo
    return self.env['sensitive.model'].create(validated_data)
```

### 2. Missing Company Filtering

**❌ Problem:**
```python
def get_all_motors(self):
    # DANGEROUS: Returns motors from all companies
    return self.env['motor'].search([])
```

**✅ Solution:**
```python
def get_all_motors(self):
    # Filter by user's allowed companies
    domain = [('company_id', 'in', self.env.companies.ids)]
    return self.env['motor'].search(domain)
```

### 3. Inadequate Input Validation

**❌ Problem:**
```python
@api.model
def create_from_api(self, vals):
    # DANGEROUS: No input validation
    return self.create(vals)
```

**✅ Solution:**
```python
@api.model
def create_from_api(self, vals):
    # Validate required fields
    required_fields = ['name', 'motor_number']
    for field in required_fields:
        if field not in vals:
            raise ValidationError(f"Missing required field: {field}")
    
    # Sanitize input
    allowed_fields = self._get_allowed_api_fields()
    vals = {k: v for k, v in vals.items() if k in allowed_fields}
    
    return self.create(vals)
```

### 4. Exposing Sensitive Data in API

**❌ Problem:**
```python
@http.route('/api/customers', auth='user', type='json')
def get_customers(self):
    # DANGEROUS: Exposes all customer data
    customers = request.env['res.partner'].search([])
    return customers.read()
```

**✅ Solution:**
```python
@http.route('/api/customers', auth='user', type='json')
def get_customers(self):
    # Filter by company and limit fields
    domain = [('company_id', 'in', request.env.companies.ids)]
    customers = request.env['res.partner'].search(domain)
    
    # Only return safe fields
    safe_fields = ['name', 'email', 'phone']
    return customers.read(safe_fields)
```

### 5. Improper Record Rule Bypass

**❌ Problem:**
```python
def get_partner_data(self, partner_id):
    # DANGEROUS: Bypasses record rules
    partner = self.env['res.partner'].sudo().browse(partner_id)
    return partner.read()
```

**✅ Solution:**
```python
def get_partner_data(self, partner_id):
    # Respect record rules
    partner = self.env['res.partner'].browse(partner_id)
    
    # Check if user has access
    try:
        partner.check_access_rights('read')
        partner.check_access_rule('read')
    except AccessError:
        raise AccessError("You don't have access to this partner")
    
    return partner.read()
```

## Security Checklist

Before deploying security-sensitive code:

- [ ] All models have appropriate access rights defined
- [ ] Record rules implement proper company filtering
- [ ] Sudo usage is minimal and justified
- [ ] User input is validated and sanitized
- [ ] API endpoints have proper authentication
- [ ] Sensitive fields are protected with groups
- [ ] Webhook signatures are verified
- [ ] Error messages don't leak sensitive information
- [ ] Security groups are properly configured
- [ ] Multi-company isolation is implemented

## Additional Resources

- [Odoo Security Documentation](https://www.odoo.com/documentation/18.0/developer/reference/backend/security.html)
- [Access Rights and Record Rules](https://www.odoo.com/documentation/18.0/developer/tutorials/getting_started/06_security.html)
- [Group Management](https://www.odoo.com/documentation/18.0/applications/general/users/access_rights.html)