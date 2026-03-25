# Odoo MCP Create/Delete Test Script

## Overview

The `test_create_delete.py` script is a **production-safe** test suite for testing the `create_record` and `delete_record` operations in the Odoo MCP client. It includes comprehensive safety features to prevent accidental data loss and ensure proper cleanup.

## Safety Features

### 1. **Identifiable Test Data**
- All test records are created with the prefix `MCP_TEST_`
- Includes timestamp in names: `MCP_TEST_Note_20260322_143522`
- Easy to identify and filter test records

### 2. **Tracked Cleanup**
- All created records are tracked in memory
- Automatic cleanup after successful tests
- Manual cleanup mode available (`--cleanup-only`)

### 3. **Verification Steps**
- Verifies record exists before deletion
- Confirms deletion was successful
- Validates field values after creation

### 4. **Dry Run Mode**
- Preview all operations without making changes
- Safe to run in production environments

### 5. **Comprehensive Logging**
- All operations logged to console
- Detailed audit trail saved to `test_create_delete.log`
- Pass/fail indicators for each test

### 6. **Error Handling**
- Graceful error recovery
- Continues testing after individual failures
- Detailed error reporting in summary

## Usage

### Basic Usage

```bash
# Run all tests
python test_create_delete.py

# Dry run (preview only)
python test_create_delete.py --dry-run

# Test specific model
python test_create_delete.py --model note.note

# Clean up test records from previous runs
python test_create_delete.py --cleanup-only

# List all test records in database
python test_create_delete.py --list-test-records
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview what would be done without making changes |
| `--model` | Test only the specified model (choices: note.note, res.partner, res.users) |
| `--cleanup-only` | Only clean up test records from previous runs |
| `--list-test-records` | List all test records currently in the database |

## Test Models

The script tests three safe models:

### 1. note.note (Notes)
- **Safest model** - no business logic attached
- Fields: name, memo
- Recommended for initial testing

### 2. res.partner (Contacts/Customers)
- Creates with `supplier_rank=0` and `customer_rank=0`
- Not linked to any business transactions
- Easy to identify and remove

### 3. res.users (Users)
- Created with `active=False` (inactive by default)
- Cannot log in or affect system
- Safe for testing user operations

## Test Scenarios

For each model, the script runs the following tests:

1. **Create Record** - Create a single test record
2. **Verify Creation** - Confirm record exists with correct data
3. **Update Record** - Update the created record (optional)
4. **Delete Record** - Delete the created record
5. **Verify Deletion** - Confirm record no longer exists

Additional batch test (note.note only):
6. **Batch Create/Delete** - Create and delete 3 records at once

## Example Output

```
============================================================
Starting Odoo MCP Create/Delete Tests
============================================================
Test Prefix: MCP_TEST_
Timestamp: 20260322_143522
Dry Run: False
============================================================

############################################################
# Testing Model: note.note
############################################################

============================================================
Test: Create record in note.note
============================================================
Model: note.note
Data: {
  "name": "MCP_TEST_Note_20260322_143522",
  "memo": "Automated test note created at 2026-03-22T14:35:22.123456"
}
✓ Created note.note with ID: 123

============================================================
Test: Verify created record in note.note
============================================================
✓ Record exists: {"id": 123, "name": "MCP_TEST_Note_20260322_143522", ...}
✓ Field 'name' matches: 'MCP_TEST_Note_20260322_143522'

============================================================
Test: Delete record from note.note
============================================================
Deleting note.note ID 123
✓ Deleted note.note ID 123

============================================================
Test: Verify record deleted from note.note
============================================================
✓ Record 123 no longer exists

############################################################
# Testing Batch Create/Delete
############################################################

============================================================
Test: Batch create/delete in note.note (3 records)
============================================================
Creating 3 records...
✓ Created record 1/3: ID 124
✓ Created record 2/3: ID 125
✓ Created record 3/3: ID 126
✓ Created 3 records: [124, 125, 126]
Deleting 3 records...
✓ Deleted 3 records

============================================================
Cleanup Phase
============================================================
✓ All records cleaned up successfully

============================================================
Test Summary
============================================================
Total Tests:  15
Passed:       15 ✓
Failed:       0
Success Rate: 100.0%
============================================================
```

## Cleanup Modes

### Automatic Cleanup
- Runs automatically after each test
- Deletes only records created during the test session
- Tracked by model and record ID

### Manual Cleanup
```bash
# Find all test records
python test_create_delete.py --list-test-records

# Interactive cleanup (with confirmation)
python test_create_delete.py --cleanup-only
```

## Log File

All test operations are logged to `test_create_delete.log`:
```
2026-03-22 14:35:22 - INFO - Starting Odoo MCP Create/Delete Tests
2026-03-22 14:35:22 - INFO - Test Prefix: MCP_TEST_
2026-03-22 14:35:22 - INFO - ✓ Created note.note with ID: 123
2026-03-22 14:35:23 - INFO - ✓ Deleted note.note ID 123
```

## Safety Checklist

Before running tests, ensure:

- [ ] **READONLY_MODE is disabled** (`READONLY_MODE=false` in .env)
- [ ] **Test database** - Use a non-production database if possible
- [ ] **Backup available** - Recent backup of production database
- [ ] **API key permissions** - API key has appropriate permissions
- [ ] **Disk space** - Sufficient space for log files

## Troubleshooting

### Issue: "READONLY_MODE is enabled"
**Solution:** Set `READONLY_MODE=false` in your `.env` file

### Issue: "Model not found"
**Solution:** Ensure the module for that model is installed in Odoo

### Issue: "Permission denied"
**Solution:** Check that your API key has write permissions

### Issue: "Records not cleaned up"
**Solution:** Run `python test_create_delete.py --cleanup-only`

## Best Practices

1. **Start with dry-run mode** to preview operations
2. **Use note.note first** as it's the safest model
3. **Check the log file** for detailed operation history
4. **Run cleanup-only** after any failed tests
5. **Test in staging** before running in production

## Extending the Script

To add test configurations for new models:

```python
TEST_CONFIGS = {
    "your.model": {
        "name": "Test Your Model",
        "fields": {
            "field1": f"{TEST_PREFIX}Value1_{TEST_TIMESTAMP}",
            "field2": "safe_default_value",
        }
    },
}
```

Add the model to `TEST_CONFIGS` dictionary with:
- `"name"`: Human-readable name for logs
- `"fields"`: Dictionary of field values for test records

## Exit Codes

- `0` - All tests passed
- `1` - One or more tests failed
- `130` - Interrupted by user (Ctrl+C)

## Contributing

When adding new tests:
1. Follow the existing test function patterns
2. Use the `TEST_PREFIX` for all test data
3. Add comprehensive error handling
4. Update this README with new test scenarios

## License

This test script is part of the Odoo MCP Client project.
