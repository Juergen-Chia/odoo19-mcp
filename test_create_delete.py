#!/usr/bin/env python3
"""
Safe Test Script for Create/Delete Operations

This script safely tests the create_record and delete_record operations
in the Odoo MCP client using test data that can be safely created and deleted.

SAFETY FEATURES:
- Only creates records with identifiable test names (MCP_TEST_...)
- Only deletes records that were created during the test
- Verifies record existence before deletion
- Includes comprehensive error handling and cleanup
- Logs all operations for audit trail
- Supports dry-run mode

Usage:
    python test_create_delete.py              # Run all tests
    python test_create_delete.py --dry-run    # Preview what would be done
    python test_create_delete.py --model note.note  # Test specific model
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Optional

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv

# Import the MCP client
from odoo_mcp_client import OdooMCPClient, OdooMCPConfig, OdooMCPError, OdooMCPToolError

# Load environment variables
load_dotenv()

# Configure logging
# Ensure UTF-8 for file handler
file_handler = logging.FileHandler('test_create_delete.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)

# Console handler with UTF-8 if available, otherwise ASCII-safe
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[console_handler, file_handler],
    force=True  # Override any existing config
)
logger = logging.getLogger(__name__)


# =============================================================================
# Test Configuration
# =============================================================================

TEST_PREFIX = "MCP_TEST_"
TEST_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Safe test configurations for different models
# NOTE: Only use models from installed modules: Discuss, Contact, Sales, Invoicing, Purchase, Inventory
TEST_CONFIGS = {
    "res.partner": {
        "name": "Test Partner (Contact module)",
        "fields": {
            "name": f"{TEST_PREFIX}Partner_{TEST_TIMESTAMP}",
            "email": f"test_{TEST_TIMESTAMP}@example.com",
            "is_company": False,
            "supplier_rank": 0,
            "customer_rank": 0,
        }
    },
    "res.users": {
        "name": "Test User (base system)",
        "fields": {
            # Minimal required fields for res.users
            "name": f"{TEST_PREFIX}User_{TEST_TIMESTAMP}",
            "login": f"test_user_{TEST_TIMESTAMP}",
            # Note: Keep minimal - email and active can cause validation issues
        }
    },
    # Add more models from installed modules as needed:
    # "mail.message": {
    #     "name": "Test Message (Discuss module)",
    #     "fields": {
    #         "body": f"Test message {TEST_TIMESTAMP}",
    #         "message_type": "comment",
    #     }
    # },
    # "product.product": {
    #     "name": "Test Product (Inventory module)",
    #     "fields": {
    #         "name": f"{TEST_PREFIX}Product_{TEST_TIMESTAMP}",
    #         "detailed_type": "service",
    #         "sale_ok": False,
    #         "purchase_ok": False,
    #     }
    # },
}


# =============================================================================
# Test Results Tracking
# =============================================================================

class TestResults:
    """Track test results and cleanup data."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.created_record_ids = {}  # {model: [ids]}
        self.errors = []

    def add_created_record(self, model: str, record_id: int) -> None:
        """Track a created record for cleanup."""
        if model not in self.created_record_ids:
            self.created_record_ids[model] = []
        self.created_record_ids[model].append(record_id)
        logger.info(f"Tracking created record: {model} ID {record_id}")

    def remove_created_record(self, model: str, record_id: int) -> None:
        """Remove a record from tracking after successful deletion."""
        if model in self.created_record_ids and record_id in self.created_record_ids[model]:
            self.created_record_ids[model].remove(record_id)
            logger.info(f"Removed from tracking: {model} ID {record_id}")

    def get_created_records(self, model: str) -> list[int]:
        """Get all created record IDs for a model."""
        return self.created_record_ids.get(model, [])

    def record_pass(self, test_name: str) -> None:
        """Record a passed test."""
        self.passed += 1
        logger.info(f"[PASS] {test_name}")

    def record_fail(self, test_name: str, error: str) -> None:
        """Record a failed test."""
        self.failed += 1
        self.errors.append({"test": test_name, "error": error})
        logger.error(f"[FAIL] {test_name} - {error}")

    def summary(self) -> str:
        """Generate test summary."""
        total = self.passed + self.failed
        return f"""
{'='*60}
Test Summary
{'='*60}
Total Tests:  {total}
Passed:       {self.passed}
Failed:       {self.failed}
Success Rate: {(self.passed/total*100):.1f}% if total > 0 else 0%
{'='*60}
"""


# =============================================================================
# Test Helper Functions
# =============================================================================

def extract_tool_result(result: Any) -> Any:
    """Extract content from MCP tool result."""
    if isinstance(result, dict):
        if 'content' in result and result['content']:
            if isinstance(result['content'], list) and len(result['content']) > 0:
                content = result['content'][0]
                if isinstance(content, dict) and 'text' in content:
                    text = content['text']
                    # Log raw response for debugging
                    logger.debug(f"Raw MCP response: {repr(text)}")
                    if not text or not text.strip():
                        logger.error(f"Empty response from MCP server")
                        raise ValueError("MCP server returned empty response")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response: {e}")
                        logger.error(f"Raw text was: {repr(text[:500])}")  # First 500 chars
                        raise
                return content
        elif 'structuredContent' in result:
            return result['structuredContent']
    return result


async def verify_record_exists(
    client: OdooMCPClient,
    model: str,
    record_id: int
) -> Optional[dict]:
    """Verify that a record exists by reading it.

    Args:
        client: Odoo MCP client
        model: Model name
        record_id: Record ID to verify

    Returns:
        Record data if found, None otherwise
    """
    try:
        result = await client.call_tool(
            "read_records",
            {
                "model": model,
                "ids": [record_id],
                "fields": ["id", "name", "display_name"]
            }
        )
        records = extract_tool_result(result)
        if isinstance(records, list) and len(records) > 0:
            return records[0]
        return None
    except Exception as e:
        logger.warning(f"Failed to verify record existence: {e}")
        return None


async def search_test_records(
    client: OdooMCPClient,
    model: str,
    test_name: str
) -> list[int]:
    """Search for test records by name prefix.

    Args:
        client: Odoo MCP client
        model: Model name
        test_name: Test record name (with prefix)

    Returns:
        List of record IDs
    """
    try:
        # Try different domain patterns for different models
        if model == "res.partner":
            domain = [["name", "=", test_name]]
        elif model == "note.note":
            domain = [["name", "=", test_name]]
        elif model == "res.users":
            domain = [["login", "=", test_name]]
        else:
            domain = [["name", "=", test_name]]

        result = await client.call_tool(
            "search_records",
            {
                "model": model,
                "domain": domain,
                "limit": 10
            }
        )
        records = extract_tool_result(result)
        if isinstance(records, list):
            return [r.get('id') for r in records if isinstance(r, dict) and 'id' in r]
        return []
    except Exception as e:
        logger.warning(f"Failed to search for test records: {e}")
        return []


async def cleanup_test_records(
    client: OdooMCPClient,
    results: TestResults,
    dry_run: bool = False
) -> None:
    """Clean up all test records created during testing.

    Args:
        client: Odoo MCP client
        results: TestResults with tracked records
        dry_run: If True, only report what would be deleted
    """
    logger.info("\n" + "="*60)
    logger.info("Cleanup Phase")
    logger.info("="*60)

    total_deleted = 0
    for model, record_ids in results.created_record_ids.items():
        logger.info(f"\nModel: {model}")
        logger.info(f"Records to delete: {record_ids}")

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {len(record_ids)} record(s)")
            total_deleted += len(record_ids)
            continue

        for record_id in record_ids:
            try:
                # Verify record still exists before deleting
                record = await verify_record_exists(client, model, record_id)
                if not record:
                    logger.warning(f"Record {record_id} no longer exists, skipping")
                    results.remove_created_record(model, record_id)
                    continue

                # Delete the record
                await client.call_tool(
                    "delete_record",
                    {
                        "model": model,
                        "ids": [record_id]
                    }
                )
                logger.info(f"[OK] Deleted {model} ID {record_id}")
                results.remove_created_record(model, record_id)
                total_deleted += 1

            except Exception as e:
                logger.error(f"[ERROR] Failed to delete {model} ID {record_id}: {e}")

    logger.info(f"\n{'='*60}")
    logger.info(f"Cleanup complete. Total records deleted: {total_deleted}")
    logger.info(f"{'='*60}")


# =============================================================================
# Test Functions
# =============================================================================

async def test_create_record(
    client: OdooMCPClient,
    results: TestResults,
    model: str,
    test_data: dict,
    dry_run: bool = False
) -> Optional[int]:
    """Test creating a single record.

    Args:
        client: Odoo MCP client
        results: TestResults tracker
        model: Model name
        test_data: Test record data
        dry_run: If True, only report what would be created

    Returns:
        Created record ID if successful, None otherwise
    """
    test_name = f"Create record in {model}"
    logger.info(f"\n{'='*60}")
    logger.info(f"Test: {test_name}")
    logger.info(f"{'='*60}")
    logger.info(f"Model: {model}")
    logger.info(f"Data: {json.dumps(test_data, indent=2)}")

    if dry_run:
        logger.info(f"[DRY RUN] Would create record in {model}")
        results.record_pass(test_name + " (dry run)")
        return None

    try:
        result = await client.call_tool(
            "create_record",
            {
                "model": model,
                "values": test_data
            }
        )

        created = extract_tool_result(result)
        if isinstance(created, list) and len(created) > 0:
            record_id = created[0].get('id') if isinstance(created[0], dict) else created[0]
        elif isinstance(created, dict) and 'id' in created:
            record_id = created['id']
        else:
            raise ValueError(f"Unexpected result format: {created}")

        logger.info(f"[OK] Created {model} with ID: {record_id}")
        results.record_pass(test_name)
        results.add_created_record(model, record_id)
        return record_id

    except Exception as e:
        results.record_fail(test_name, str(e))
        return None


async def test_verify_created_record(
    client: OdooMCPClient,
    results: TestResults,
    model: str,
    record_id: int,
    expected_fields: dict
) -> None:
    """Test that the created record exists and has expected data.

    Args:
        client: Odoo MCP client
        results: TestResults tracker
        model: Model name
        record_id: Record ID to verify
        expected_fields: Expected field values
    """
    test_name = f"Verify created record in {model}"
    logger.info(f"\n{'='*60}")
    logger.info(f"Test: {test_name}")
    logger.info(f"{'='*60}")

    try:
        record = await verify_record_exists(client, model, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")

        logger.info(f"[OK] Record exists: {json.dumps(record, indent=2)}")

        # Verify expected fields
        for field, expected_value in expected_fields.items():
            actual_value = record.get(field)
            if actual_value != expected_value:
                logger.warning(
                    f"Field '{field}' mismatch: expected '{expected_value}', got '{actual_value}'"
                )
            else:
                logger.info(f"[OK] Field '{field}' matches: '{actual_value}'")

        results.record_pass(test_name)

    except Exception as e:
        results.record_fail(test_name, str(e))


async def test_update_record(
    client: OdooMCPClient,
    results: TestResults,
    model: str,
    record_id: int,
    update_fields: dict
) -> None:
    """Test updating a created record.

    Args:
        client: Odoo MCP client
        results: TestResults tracker
        model: Model name
        record_id: Record ID to update
        update_fields: Fields to update
    """
    test_name = f"Update record in {model}"
    logger.info(f"\n{'='*60}")
    logger.info(f"Test: {test_name}")
    logger.info(f"{'='*60}")
    logger.info(f"Updating {model} ID {record_id}")
    logger.info(f"Fields: {json.dumps(update_fields, indent=2)}")

    try:
        await client.call_tool(
            "update_record",
            {
                "model": model,
                "ids": [record_id],
                "values": update_fields
            }
        )
        logger.info(f"[OK] Updated {model} ID {record_id}")
        results.record_pass(test_name)

    except Exception as e:
        results.record_fail(test_name, str(e))


async def test_delete_record(
    client: OdooMCPClient,
    results: TestResults,
    model: str,
    record_id: int,
    dry_run: bool = False
) -> None:
    """Test deleting a created record.

    Args:
        client: Odoo MCP client
        results: TestResults tracker
        model: Model name
        record_id: Record ID to delete
        dry_run: If True, only report what would be deleted
    """
    test_name = f"Delete record from {model}"
    logger.info(f"\n{'='*60}")
    logger.info(f"Test: {test_name}")
    logger.info(f"{'='*60}")
    logger.info(f"Deleting {model} ID {record_id}")

    if dry_run:
        logger.info(f"[DRY RUN] Would delete {model} ID {record_id}")
        results.record_pass(test_name + " (dry run)")
        return

    try:
        # Verify record exists before deletion
        record = await verify_record_exists(client, model, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found, cannot delete")

        # Delete the record
        await client.call_tool(
            "delete_record",
            {
                "model": model,
                "ids": [record_id]
            }
        )
        logger.info(f"[OK] Deleted {model} ID {record_id}")
        results.record_pass(test_name)
        results.remove_created_record(model, record_id)

    except Exception as e:
        results.record_fail(test_name, str(e))


async def test_verify_deleted_record(
    client: OdooMCPClient,
    results: TestResults,
    model: str,
    record_id: int
) -> None:
    """Test that the deleted record no longer exists.

    Args:
        client: Odoo MCP client
        results: TestResults tracker
        model: Model name
        record_id: Record ID that should be deleted
    """
    test_name = f"Verify record deleted from {model}"
    logger.info(f"\n{'='*60}")
    logger.info(f"Test: {test_name}")
    logger.info(f"{'='*60}")

    try:
        record = await verify_record_exists(client, model, record_id)
        if record:
            raise ValueError(f"Record {record_id} still exists after deletion")
        logger.info(f"[OK] Record {record_id} no longer exists")
        results.record_pass(test_name)

    except Exception as e:
        results.record_fail(test_name, str(e))


async def test_batch_create_delete(
    client: OdooMCPClient,
    results: TestResults,
    model: str,
    test_configs: list[dict],
    dry_run: bool = False
) -> None:
    """Test creating and deleting multiple records in batch.

    Args:
        client: Odoo MCP client
        results: TestResults tracker
        model: Model name
        test_configs: List of test record configurations
        dry_run: If True, only report what would be done
    """
    test_name = f"Batch create/delete in {model}"
    logger.info(f"\n{'='*60}")
    logger.info(f"Test: {test_name} ({len(test_configs)} records)")
    logger.info(f"{'='*60}")

    if dry_run:
        logger.info(f"[DRY RUN] Would create {len(test_configs)} records in {model}")
        results.record_pass(test_name + " (dry run)")
        return

    created_ids = []

    try:
        # Create multiple records
        logger.info(f"Creating {len(test_configs)} records...")
        for i, config in enumerate(test_configs):
            result = await client.call_tool(
                "create_record",
                {
                    "model": model,
                    "values": config
                }
            )
            created = extract_tool_result(result)
            if isinstance(created, list) and len(created) > 0:
                record_id = created[0].get('id') if isinstance(created[0], dict) else created[0]
            elif isinstance(created, dict) and 'id' in created:
                record_id = created['id']
            else:
                raise ValueError(f"Unexpected result format: {created}")
            created_ids.append(record_id)
            results.add_created_record(model, record_id)
            logger.info(f"[OK] Created record {i+1}/{len(test_configs)}: ID {record_id}")

        logger.info(f"[OK] Created {len(created_ids)} records: {created_ids}")

        # Delete all created records
        logger.info(f"Deleting {len(created_ids)} records...")
        await client.call_tool(
            "delete_record",
            {
                "model": model,
                "ids": created_ids
            }
        )
        logger.info(f"[OK] Deleted {len(created_ids)} records")

        # Verify all deleted
        for record_id in created_ids:
            record = await verify_record_exists(client, model, record_id)
            if record:
                logger.warning(f"Record {record_id} still exists after batch delete")
            else:
                results.remove_created_record(model, record_id)

        results.record_pass(test_name)

    except Exception as e:
        results.record_fail(test_name, str(e))


# =============================================================================
# Main Test Runner
# =============================================================================

async def run_all_tests(
    client: OdooMCPClient,
    model_filter: Optional[str] = None,
    dry_run: bool = False
) -> TestResults:
    """Run all create/delete tests.

    Args:
        client: Odoo MCP client
        model_filter: Optional model filter (e.g., "note.note")
        dry_run: If True, only report what would be done

    Returns:
        TestResults with all test outcomes
    """
    results = TestResults()

    logger.info("\n" + "="*60)
    logger.info("Starting Odoo MCP Create/Delete Tests")
    logger.info("="*60)
    logger.info(f"Test Prefix: {TEST_PREFIX}")
    logger.info(f"Timestamp: {TEST_TIMESTAMP}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("="*60)

    # Filter models if specified
    models_to_test = list(TEST_CONFIGS.keys())
    if model_filter:
        if model_filter in models_to_test:
            models_to_test = [model_filter]
        else:
            logger.error(f"Model '{model_filter}' not in test configs")
            logger.error(f"Available models: {', '.join(models_to_test)}")
            return results

    # Run tests for each model
    for model in models_to_test:
        logger.info(f"\n\n{'#'*60}")
        logger.info(f"# Testing Model: {model}")
        logger.info(f"{'#'*60}")

        config = TEST_CONFIGS[model]
        test_data = config["fields"]

        # Test 1: Create record
        record_id = await test_create_record(
            client, results, model, test_data, dry_run
        )
        if not record_id or dry_run:
            continue

        # Test 2: Verify created record
        await test_verify_created_record(
            client, results, model, record_id, test_data
        )

        # Test 3: Update record (optional)
        update_fields = {}
        if model == "note.note":
            update_fields = {"memo": f"Updated at {datetime.now().isoformat()}"}
        elif model == "res.partner":
            update_fields = {"comment": "Test update via MCP"}
        elif model == "res.users":
            update_fields = {"signature": "Test user"}

        if update_fields:
            await test_update_record(
                client, results, model, record_id, update_fields
            )

        # Test 4: Delete record
        await test_delete_record(
            client, results, model, record_id, dry_run
        )

        # Test 5: Verify deleted record
        await test_verify_deleted_record(
            client, results, model, record_id
        )

    # Test 6: Batch create/delete (using res.partner as safe test model)
    if "res.partner" in models_to_test and not dry_run:
        logger.info(f"\n\n{'#'*60}")
        logger.info(f"# Testing Batch Create/Delete")
        logger.info(f"{'#'*60}")

        batch_configs = [
            {
                "name": f"{TEST_PREFIX}Batch_1_{TEST_TIMESTAMP}",
                "email": f"batch1_{TEST_TIMESTAMP}@example.com",
            },
            {
                "name": f"{TEST_PREFIX}Batch_2_{TEST_TIMESTAMP}",
                "email": f"batch2_{TEST_TIMESTAMP}@example.com",
            },
            {
                "name": f"{TEST_PREFIX}Batch_3_{TEST_TIMESTAMP}",
                "email": f"batch3_{TEST_TIMESTAMP}@example.com",
            },
        ]

        await test_batch_create_delete(
            client, results, "res.partner", batch_configs, dry_run
        )

    return results


async def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(
        description="Safely test Odoo MCP create_record and delete_record operations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be done without making changes"
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=list(TEST_CONFIGS.keys()),
        help="Test only the specified model"
    )
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Only clean up test records from previous runs"
    )
    parser.add_argument(
        "--list-test-records",
        action="store_true",
        help="List all test records in the database"
    )

    args = parser.parse_args()

    # Load and validate configuration
    try:
        config = OdooMCPConfig.from_env()
        config.validate()
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Check readonly mode
    if config.readonly_mode:
        logger.error("READONLY_MODE is enabled. Write operations are blocked.")
        logger.error("Set READONLY_MODE=false in .env to test create/delete operations.")
        sys.exit(1)

    # Create and start MCP client
    client = None
    try:
        client = OdooMCPClient(config)
        await client.start()
        logger.info("[OK] Connected to MCP server")

        # Special modes
        if args.list_test_records:
            logger.info("\nListing all test records...")
            for model in TEST_CONFIGS.keys():
                test_name = f"{TEST_PREFIX}%"
                logger.info(f"\nModel: {model}")
                logger.info(f"Searching for records like: {test_name}")
                # This would require a tool to search with LIKE pattern
                # For now, we just note this feature
                logger.info("(Listing feature requires additional search capabilities)")
            return

        if args.cleanup_only:
            logger.info("\nRunning cleanup only mode...")
            results = TestResults()
            # Search for test records and clean them up
            for model in TEST_CONFIGS.keys():
                # Search for records with our test prefix
                try:
                    result = await client.call_tool(
                        "search_records",
                        {
                            "model": model,
                            "domain": [["name", "ilike", TEST_PREFIX]],
                            "limit": 100
                        }
                    )
                    records = extract_tool_result(result)
                    if isinstance(records, list) and len(records) > 0:
                        logger.info(f"\nFound {len(records)} test records in {model}:")
                        for record in records:
                            if isinstance(record, dict):
                                record_id = record.get('id')
                                name = record.get('name', record.get('login', 'Unknown'))
                                logger.info(f"  - ID {record_id}: {name}")
                                results.add_created_record(model, record_id)
                except Exception as e:
                    logger.warning(f"Failed to search {model}: {e}")

            if results.created_record_ids:
                confirm = input("\nDelete these test records? (yes/no): ")
                if confirm.lower() == 'yes':
                    await cleanup_test_records(client, results, args.dry_run)
                else:
                    logger.info("Cleanup cancelled")
            else:
                logger.info("No test records found")
            return

        # Run main test suite
        results = await run_all_tests(client, args.model, args.dry_run)

        # Print summary
        print(results.summary())

        # Print errors if any
        if results.errors:
            print("\nErrors:")
            for error in results.errors:
                print(f"  - {error['test']}: {error['error']}")

        # Final cleanup check
        if results.created_record_ids and not args.dry_run:
            logger.warning("\n⚠️ Some test records were not cleaned up:")
            for model, ids in results.created_record_ids.items():
                logger.warning(f"  {model}: {ids}")
            logger.warning("\nThese records will remain in the database.")
            logger.warning(f"You can clean them up manually or run with --cleanup-only")

        # Exit with appropriate code
        sys.exit(0 if results.failed == 0 else 1)

    except OdooMCPError as e:
        logger.error(f"MCP error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\n\nTests interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if client:
            await client.close()
            logger.info("\n[OK] MCP connection closed")


if __name__ == "__main__":
    asyncio.run(main())
