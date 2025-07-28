# 🎯 Quick Agent Reference

## When You Say... → Claude Uses...

### 🐛 **ERRORS** → Debugger

- "I'm getting this error..."
- "AttributeError: ..."
- "It's failing with..."
- "Stack trace shows..."
- **Command**: `/debug`

### 📋 **PLANNING** → Planner

- "I want to add..."
- "How should I implement..."
- "Design a feature for..."
- "Break down this task..."
- **Command**: `/plan`

### 🔧 **CLEANUP** → Refactor

- "Clean up this code"
- "Update all occurrences of..."
- "Make this consistent"
- "Remove redundant..."
- **Command**: `/refactor`

### 🏹 **RESEARCH** → Archer

- "How does Odoo..."
- "Find examples of..."
- "What's the pattern for..."
- "Show me how to..."
- **Command**: `/archer`

### 🔍 **TESTING** → Scout

- "Write tests for..."
- "Create test coverage..."
- "Test is failing..."
- "Add unit tests..."
- **Command**: `/test` (for running) or `/scout` (for writing)

### 🔬 **QUALITY** → Inspector

- "Check code quality"
- "Find issues in..."
- "Analyze performance"
- "Review this code"
- **Command**: `/quality`

### 🚢 **CONTAINERS** → Dock

- "Container won't start"
- "Check docker logs"
- "Module won't update"
- "Database connection..."
- **Command**: `/docker`

### 🛍️ **SHOPIFY** → Shopkeeper

- "Sync products..."
- "Shopify integration..."
- "GraphQL query..."
- "Import from Shopify..."
- **Command**: `/sync`

### 🦉 **FRONTEND** → Owl

- "JavaScript component..."
- "Owl.js widget..."
- "Frontend not working..."
- "Add UI element..."
- **Command**: `/owl`

## 🚀 One Command to Rule Them All

**Can't remember which agent?** Just use:

```
/help-me [describe your task]
```

Claude will automatically pick the right agent!