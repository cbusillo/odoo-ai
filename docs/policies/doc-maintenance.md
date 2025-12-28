Title: Documentation Maintenance Patterns

Use these guidelines to keep documentation accurate, concise, and discoverable.

## Documentation Structure Reference

### Core Documentation Files

- `docs/README.md` - Documentation index
- `docs/testing.md` - Testing overview and CLI pointers
- `docs/architecture.md` - System architecture overview

### Agent Documentation Hierarchy

- `docs/roles/` - Role stubs and collaboration guidance

### Style Guidelines Structure

- `docs/policies/coding-standards.md` - Universal code quality principles
- `docs/style/python.md` - Python-specific standards
- `docs/odoo/workflow.md` - Odoo workflow and conventions
- `docs/style/javascript.md` - JavaScript/Owl.js standards
- `docs/style/testing.md` - Test quality requirements

### Reference Documentation

- `docs/references/` - Technical reference materials
- Module-specific docs (e.g., `addons/product_connect/docs/`)

## Detailed Maintenance Patterns

### Consistency Verification

- Cross‑references: scan `@docs/` handles and confirm targets exist.
- Internal links: scan Markdown links and verify target files resolve.
- Versions: spot‑check Odoo/Python/PostgreSQL/Compose references.

### Code ↔ Docs Alignment

- When major models or workflows change, update relevant pages in style/odoo/workflows.
- Keep role stubs focused and current.

### Version Updates

- Check Odoo/Shopify docs URLs periodically and update if structures change.
- Confirm version references match actual runtime/CI.

## Comprehensive Documentation Workflows

### Periodic Assessment

- Verify `docs/README.md` ToC coverage and accuracy.
- Prune or update stale module docs.
- Confirm acceptance gates and workflows match current practice.

### Targeted Verification

- Compare critical model docs to code when behavior changes.
- Validate external links on recently edited pages.

### Update Execution

- Group changes (links/content/structure) and submit focused PRs with a clear rationale.
- Update the ToC alongside structure changes.

## Quality Assurance Patterns

### Post-Update Quality Checks

### Post-Update Checks

- Scan for TODO/FIXME markers and resolve.
- Validate Markdown links and @docs/ handles.
- Ensure any code examples are current and minimal.
- If you changed behavior or APIs, update the relevant pages in this PR.

### Documentation Standards Enforcement

```python
def enforce_documentation_standards(file_path):
    content = Read(file_path)
    violations = []
    
    # Header hierarchy check
    headers = extract_headers(content)
    hierarchy_issues = validate_header_hierarchy(headers)
    violations.extend(hierarchy_issues)
    
    # Code block validation
    code_blocks = extract_code_blocks(content)
    for block in code_blocks:
        if not validate_code_block(block):
            violations.append(f"Invalid code block at line {block.line}")
    
    # Cross-reference format check
    references = extract_cross_references(content)
    for ref in references:
        if not validate_reference_format(ref):
            violations.append(f"Invalid reference format: {ref}")
    
    return violations
```

## Special Case Handling Patterns

### External Documentation Synchronization

```python
def sync_external_documentation():
    # Odoo version updates
    def update_odoo_references():
        current_odoo = WebSearch(query="Odoo 18 latest documentation structure")
        odoo_links = find_odoo_links("docs/")
        
        for link in odoo_links:
            updated_link = modernize_odoo_link(link, current_odoo)
            if updated_link != link:
                schedule_link_update(link, updated_link)
    
    # Shopify API synchronization
    def update_shopify_references():
        current_api = WebSearch(query="Shopify GraphQL API 2025-04 latest")
        api_refs = find_shopify_api_references()
        
        for ref in api_refs:
            if ref['version'] != current_api['version']:
                schedule_api_update(ref, current_api)
    
    # Python feature updates
    def update_python_references():
        python_features = find_python_feature_references()
        for feature in python_features:
            if feature['version'] < '3.13':
                suggest_modern_alternative(feature)
```

### Roles & Tooling Docs

- Keep role stubs minimal; link out to workflows/style as needed.
- Keep tooling pages authoritative and brief.

## Advanced Link Management

### Link Validation and Updates

```python
def advanced_link_management():
    # Categorize all links
    all_links = extract_all_links("docs/")
    link_categories = {
        'internal': [l for l in all_links if is_internal_link(l)],
        'external_docs': [l for l in all_links if is_external_doc_link(l)],
        'code_references': [l for l in all_links if is_code_reference(l)],
        'api_endpoints': [l for l in all_links if is_api_endpoint(l)]
    }
    
    # Validate each category
    validation_results = {}
    for category, links in link_categories.items():
        validation_results[category] = validate_link_category(links, category)
    
    # Generate update plan
    update_plan = generate_link_update_plan(validation_results)
    
    return update_plan

def validate_link_category(links, category):
    if category == 'internal':
        return validate_internal_links(links)
    elif category == 'external_docs':
        return validate_external_documentation_links(links)
    elif category == 'code_references':
        return validate_code_reference_links(links)
    elif category == 'api_endpoints':
        return validate_api_endpoint_links(links)
```
