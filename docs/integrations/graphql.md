Title: GraphQL Patterns (Shopify)

## GraphQL Query Structure

### Product Query
```graphql
query GetProducts($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    edges {
      node {
        id
        title
        handle
        descriptionHtml
        vendor
        productType
        tags
        variants(first: 100) {
          edges {
            node {
              id
              sku
              price
              compareAtPrice
              availableForSale
              inventoryQuantity
            }
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

### Order Query
```graphql
query GetOrder($id: ID!) {
  order(id: $id) {
    id
    name
    createdAt
    fulfillmentStatus
    financialStatus
    customer {
      id
      email
      firstName
      lastName
    }
    lineItems(first: 250) {
      edges {
        node {
          id
          quantity
          variant {
            id
            sku
          }
        }
      }
    }
  }
}
```

## Mutation Patterns

### Update Product
```graphql
mutation UpdateProduct($input: ProductInput!) {
  productUpdate(input: $input) {
    product {
      id
      title
    }
    userErrors {
      field
      message
    }
  }
}
```

### Create Variant
```graphql
mutation CreateVariant($input: ProductVariantInput!) {
  productVariantCreate(input: $input) {
    productVariant {
      id
      sku
    }
    userErrors {
      field
      message
    }
  }
}
```

## Error Handling

### GraphQL Error Types
```python
# API errors
if 'errors' in result:
    for error in result['errors']:
        if error.get('extensions', {}).get('code') == 'THROTTLED':
            # Handle rate limiting
            
# User errors (validation)
if result.get('data', {}).get('productUpdate', {}).get('userErrors'):
    for error in result['data']['productUpdate']['userErrors']:
        # Handle field-specific errors
```

### Rate Limiting
```python
# Shopify GraphQL uses a cost‑based throttle. Do not hard‑code request/second.
# Inspect the `extensions.cost.throttleStatus` fields and back off dynamically.

cost = result.get('extensions', {}).get('cost', {})
throttle = cost.get('throttleStatus', {})
currently_available = throttle.get('currentlyAvailable', 0)
restore_rate = throttle.get('restoreRate', 0)  # tokens per second

if currently_available < 100:
    # Back off proportionally to remaining capacity
    sleep_seconds = max(0.5, (100 - currently_available) / max(1, restore_rate))
    time.sleep(sleep_seconds)
```

## Pagination Best Practices

### Cursor-Based Pagination
```python
def fetch_all_products():
    has_next = True
    after = None
    
    while has_next:
        result = client.execute(
            PRODUCTS_QUERY,
            {'first': 250, 'after': after}
        )
        
        # Process products
        edges = result['data']['products']['edges']
        for edge in edges:
            yield edge['node']
        
        # Check for next page
        page_info = result['data']['products']['pageInfo']
        has_next = page_info['hasNextPage']
        after = page_info['endCursor']
```

## Bulk Operations

### Bulk Query
```graphql
mutation BulkQuery($query: String!) {
  bulkOperationRunQuery(query: $query) {
    bulkOperation {
      id
      status
      url
    }
    userErrors {
      field
      message
    }
  }
}
```

### Poll for Results
```python
def wait_for_bulk_operation(operation_id):
    while True:
        result = client.execute(
            CHECK_BULK_STATUS,
            {'id': operation_id}
        )
        
        status = result['data']['node']['status']
        if status == 'COMPLETED':
            return result['data']['node']['url']
        elif status == 'FAILED':
            raise Exception("Bulk operation failed")
        
        time.sleep(5)
```

## Common Issues

### ID Format
```python
# Shopify uses global IDs
# Format: gid://shopify/Product/123456789

# Extract numeric ID
numeric_id = shopify_id.split('/')[-1]

# Construct global ID
global_id = f"gid://shopify/Product/{numeric_id}"
```

### Metafield Handling
```graphql
# Query metafields
metafields(first: 10, namespace: "custom") {
  edges {
    node {
      key
      value
      type
    }
  }
}

# Update metafields
metafields: [
  {
    namespace: "custom"
    key: "odoo_id"
    value: "123"
    type: "single_line_text_field"
  }
]
```
