# 📝 Doc Agent - Documentation Maintenance Patterns

This file contains detailed documentation maintenance patterns and workflows extracted from the Doc agent documentation.


## Documentation Structure Reference

### Core Documentation Files

- `CLAUDE.md` - Claude Code guidance and project patterns
- `docs/DOCUMENTATION.md` - Documentation index and external references
- `docs/TESTING.md` - Testing procedures and requirements
- `docs/STYLE_GUIDE.md` - Code style standards
- `docs/ARCHITECTURE.md` - System architecture overview

### Agent Documentation Hierarchy

- `docs/agents/README.md` - Agent overview and collaboration guide
- `docs/agents/*.md` - Individual agent instructions
- `docs/agents/*/` - Agent-specific sub-documentation

### Style Guidelines Structure

- `docs/style/CORE.md` - Universal code quality principles
- `docs/style/PYTHON.md` - Python-specific standards
- `docs/style/ODOO.md` - Odoo framework conventions
- `docs/style/JAVASCRIPT.md` - JavaScript/Owl.js standards
- `docs/style/TESTING.md` - Test quality requirements

### Reference Documentation

- `docs/references/` - Technical reference materials
- Module-specific docs (e.g., `addons/product_connect/docs/`)

## Detailed Maintenance Patterns

### Consistency Verification Workflows

```python
# Cross-reference validation
def verify_cross_references():
    # Check all @docs/ references are valid
    refs = Grep(pattern="@docs/agents/", path="docs/agents/", output_mode="content")
    for ref in refs:
        target_path = extract_path(ref)
        try:
            Read(target_path)
        except FileNotFoundError:
            print(f"Broken reference: {ref} -> {target_path}")

# Internal link validation
def check_internal_links():
    links = Grep(pattern="\[.*\]\(.*\.md\)", path="docs/", output_mode="content")
    broken_links = []
    for link in links:
        target = extract_markdown_link(link)
        if not file_exists(target):
            broken_links.append(link)
    return broken_links

# Version consistency check
def verify_version_references():
    version_refs = Grep(
        pattern="Odoo \d+|Python \d\.\d+|PostgreSQL \d+", 
        path="docs/", 
        output_mode="content"
    )
    return analyze_version_consistency(version_refs)
```

### Code-Documentation Alignment

```python
# Model documentation coverage
def verify_model_documentation():
    # Find all models in codebase
    models = mcp__odoo-intelligence__model_query(operation="search", pattern=".*")
    
    # Check each model has documentation
    undocumented = []
    for model in models:
        doc_exists = search_model_docs(model['name'])
        if not doc_exists:
            undocumented.append(model)
    
    return undocumented

# Agent documentation synchronization
def sync_agent_documentation():
    # Get all agent files
    agent_files = Glob(pattern="docs/agents/*.md")
    
    # Read README.md agent table
    readme = Read("docs/agents/README.md")
    
    # Check for mismatches
    table_agents = extract_agents_from_table(readme)
    file_agents = [extract_agent_name(f) for f in agent_files]
    
    missing_from_table = set(file_agents) - set(table_agents)
    missing_files = set(table_agents) - set(file_agents)
    
    return {'missing_from_table': missing_from_table, 'missing_files': missing_files}
```

### Version Update Workflows

```python
# External documentation link updates
def update_external_links():
    # Check Odoo documentation
    odoo_info = WebSearch(query="Odoo 18 documentation latest URL structure")
    
    # Check Shopify API version
    shopify_info = WebSearch(query="Shopify GraphQL API latest version 2025")
    
    # Update documentation with current information
    updates = prepare_link_updates(odoo_info, shopify_info)
    apply_bulk_updates(updates)

# Technology version synchronization
def sync_technology_versions():
    # Define current versions
    current_versions = {
        'Python': '3.12+',
        'PostgreSQL': '17',
        'Odoo': '18',
        'Docker Compose': 'v2'
    }
    
    # Find all version references
    for tech, version in current_versions.items():
        old_pattern = f"{tech} \\d+(\\.\\d+)?"
        new_value = f"{tech} {version}"
        
        files_to_update = Grep(pattern=old_pattern, path="docs/", output_mode="files_with_matches")
        
        for file in files_to_update:
            update_version_in_file(file, tech, version)
```

## Comprehensive Documentation Workflows

### Assessment Phase Patterns

```python
def comprehensive_assessment():
    # Module structure analysis
    modules = ['product_connect', 'disable_odoo_online']
    for module in modules:
        structure = mcp__odoo-intelligence__module_structure(module_name=module)
        doc_coverage = assess_documentation_coverage(structure)
        
    # Documentation index verification
    index = Read("docs/DOCUMENTATION.md")
    index_accuracy = verify_index_accuracy(index)
    
    # Agent capability alignment
    agents = Glob(pattern="docs/agents/*.md")
    capability_sync = verify_agent_capabilities(agents)
    
    return {
        'module_coverage': doc_coverage,
        'index_accuracy': index_accuracy,
        'agent_sync': capability_sync
    }
```

### Verification Phase Patterns

```python
def technical_verification():
    # Model information accuracy
    documented_models = extract_documented_models()
    for model_name in documented_models:
        actual_info = mcp__odoo-intelligence__model_query(operation="info", model_name=model_name)
        doc_info = extract_model_doc_info(model_name)
        discrepancies = compare_model_info(actual_info, doc_info)
        
        if discrepancies:
            flag_for_update(model_name, discrepancies)
    
    # External link validation
    external_links = extract_external_links("docs/")
    for link in external_links:
        status = validate_external_link(link)
        if status != 'valid':
            flag_broken_link(link, status)
    
    # API endpoint verification
    api_refs = find_api_references()
    for api_ref in api_refs:
        verify_api_endpoint(api_ref)
```

### Update Phase Implementation

```python
def execute_documentation_updates(updates):
    # Categorize updates by type
    link_updates = [u for u in updates if u['type'] == 'link']
    content_updates = [u for u in updates if u['type'] == 'content']
    structure_updates = [u for u in updates if u['type'] == 'structure']
    
    # Handle link updates (bulk operation)
    if link_updates:
        for file_path, link_changes in group_by_file(link_updates):
            edits = [
                {
                    'old_string': change['old_link'],
                    'new_string': change['new_link']
                }
                for change in link_changes
            ]
            MultiEdit(file_path=file_path, edits=edits)
    
    # Handle content updates (careful review needed)
    for update in content_updates:
        Edit(
            file_path=update['file'],
            old_string=update['old_content'],
            new_string=update['new_content']
        )
    
    # Handle structure updates (new files/reorganization)
    for update in structure_updates:
        handle_structural_change(update)
```

## Quality Assurance Patterns

### Post-Update Quality Checks

```python
def post_update_quality_check():
    # Check for TODO/FIXME markers
    issues = Grep(pattern="TODO|FIXME|XXX", path="docs/", output_mode="content")
    
    # Verify markdown syntax
    markdown_files = Glob(pattern="docs/**/*.md")
    syntax_errors = []
    for file in markdown_files:
        errors = validate_markdown_syntax(file)
        if errors:
            syntax_errors.append({'file': file, 'errors': errors})
    
    # Check cross-reference integrity
    broken_refs = verify_all_cross_references()
    
    # Validate code examples
    code_examples = extract_code_examples("docs/")
    invalid_examples = validate_code_examples(code_examples)
    
    return {
        'pending_issues': issues,
        'syntax_errors': syntax_errors,
        'broken_refs': broken_refs,
        'invalid_examples': invalid_examples
    }
```

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
            if feature['version'] < '3.12':
                suggest_modern_alternative(feature)
```

### Agent Documentation Evolution

```python
def evolve_agent_documentation():
    # New agent integration
    def integrate_new_agent(agent_name, capabilities):
        # Update README.md table
        readme = Read("docs/agents/README.md")
        new_row = generate_agent_table_row(agent_name, capabilities)
        updated_readme = insert_agent_row(readme, new_row)
        Write("docs/agents/README.md", updated_readme)
        
        # Update collaboration matrix
        matrix = extract_collaboration_matrix(readme)
        updated_matrix = add_agent_to_matrix(matrix, agent_name, capabilities)
        update_collaboration_section(updated_matrix)
    
    # Tool capability updates
    def update_tool_capabilities():
        shared_tools = Read("docs/system/SHARED_TOOLS.md")
        current_tools = analyze_available_tools()
        
        tool_diff = compare_tool_lists(shared_tools, current_tools)
        if tool_diff['new_tools'] or tool_diff['removed_tools']:
            updated_shared_tools = reconcile_tool_documentation(tool_diff)
            Write("docs/system/SHARED_TOOLS.md", updated_shared_tools)
```

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