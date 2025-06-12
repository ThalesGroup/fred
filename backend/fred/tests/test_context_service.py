# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import tempfile
import pathlib
from io import BytesIO

from fred.context.context_service import ContextService

class TestContextService(unittest.TestCase):
    
    def setUp(self):
        # Create a temporary directory for tests in local mode
        self.temp_dir = tempfile.TemporaryDirectory()
        self.local_path = pathlib.Path(self.temp_dir.name)
        
        # Mock for MinIO
        self.mock_minio = Mock()
        self.mock_minio.bucket_exists.return_value = True  # Avoids bucket creation
        
        # Create instances to test
        self.local_service = ContextService(minio_client=None, local_base_dir=self.local_path)
        self.minio_service = ContextService(minio_client=self.mock_minio, bucket_name="test-bucket")
    
    def tearDown(self):
        # Clean up temporary directory
        self.temp_dir.cleanup()
    
    def test_local_storage_init(self):
        """Tests initialization in local storage mode"""
        self.assertIsNone(self.local_service.minio_client)
        self.assertEqual(self.local_service.local_base_dir, self.local_path)
        self.assertTrue(self.local_path.exists())
        self.assertTrue(self.local_path.is_dir())
    
    def test_minio_storage_init(self):
        """Tests initialization in MinIO mode"""
        self.assertEqual(self.minio_service.minio_client, self.mock_minio)
        self.assertEqual(self.minio_service.bucket_name, "test-bucket")
        # Verify that the method to ensure bucket existence was called
        self.mock_minio.bucket_exists.assert_called_once_with("test-bucket")
    
    def test_get_contexts_local_empty(self):
        """Tests retrieving local contexts when none exist"""
        contexts = self.local_service.get_contexts("test-agent")
        self.assertEqual(contexts, [])
    
    def test_save_and_get_contexts_local(self):
        """Tests saving and retrieving contexts in local mode"""
        # Create a context
        context = {
            "title": "Test Context",
            "content": "This is a test context"
        }
        
        # Save the context
        saved_context = self.local_service.save_context("test-agent", context)
        
        # Verify that the ID was generated
        self.assertIn("id", saved_context)
        self.assertIsNotNone(saved_context["id"])
        self.assertEqual(saved_context["title"], "Test Context")
        self.assertEqual(saved_context["content"], "This is a test context")
        
        # Retrieve contexts
        contexts = self.local_service.get_contexts("test-agent")
        
        # Verify that the context is retrieved correctly
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0]["id"], saved_context["id"])
        self.assertEqual(contexts[0]["title"], "Test Context")
        self.assertEqual(contexts[0]["content"], "This is a test context")
        
        # Verify that the file was created
        # Note: We use the format without dash as defined in _get_agent_object_name
        file_path = self.local_path / "test-agent_contexts.json"
        self.assertTrue(file_path.exists(), f"The file {file_path} should exist")
        
        # Verify file content
        with open(file_path, 'r') as f:
            saved_data = json.load(f)
            self.assertEqual(len(saved_data), 1)
            self.assertEqual(saved_data[0]["id"], saved_context["id"])
    
    def test_update_context_local(self):
        """Tests updating an existing context in local mode"""
        # Create a context
        context = {
            "title": "Test Context",
            "content": "This is a test context"
        }
        
        # Save the context
        saved_context = self.local_service.save_context("test-agent", context)
        context_id = saved_context["id"]
        
        # Update the context
        updated_context = {
            "id": context_id,
            "title": "Updated Context",
            "content": "This is an updated test context"
        }
        
        result = self.local_service.save_context("test-agent", updated_context)
        
        # Verify that the ID is the same
        self.assertEqual(result["id"], context_id)
        self.assertEqual(result["title"], "Updated Context")
        
        # Retrieve contexts
        contexts = self.local_service.get_contexts("test-agent")
        
        # Verify that there is still only one context
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0]["title"], "Updated Context")
    
    def test_delete_context_local(self):
        """Tests deleting a context in local mode"""
        # Create a context
        context = {
            "title": "Test Context",
            "content": "This is a test context"
        }
        
        # Save the context
        saved_context = self.local_service.save_context("test-agent", context)
        context_id = saved_context["id"]
        
        # Verify that the context exists
        contexts = self.local_service.get_contexts("test-agent")
        self.assertEqual(len(contexts), 1)
        
        # Delete the context
        result = self.local_service.delete_context("test-agent", context_id)
        self.assertTrue(result)
        
        # Verify that the context has been deleted
        contexts = self.local_service.get_contexts("test-agent")
        self.assertEqual(len(contexts), 0)
    
    def test_delete_nonexistent_context_local(self):
        """Tests deleting a nonexistent context in local mode"""
        result = self.local_service.delete_context("test-agent", "nonexistent-id")
        self.assertFalse(result)
    
    def test_get_contexts_minio(self):
        """Tests retrieving contexts in MinIO mode"""
        # Configure mocks
        mock_response = Mock()
        mock_response.read.return_value = b'[{"id":"123","title":"Minio Context","content":"Minio content"}]'
        mock_response.close = Mock()
        
        self.mock_minio.get_object.return_value = mock_response
        
        # Call method to test
        contexts = self.minio_service.get_contexts("test-agent")
        
        # Verify calls
        self.mock_minio.get_object.assert_called_once_with("test-bucket", "test-agent_contexts.json")
        mock_response.read.assert_called_once()
        
        # Verify result
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0]["id"], "123")
        self.assertEqual(contexts[0]["title"], "Minio Context")
    
    def test_save_context_minio(self):
        """Tests saving a context in MinIO mode"""
        # Configure mocks
        self.mock_minio.get_object.side_effect = Exception("Object not found")
        
        # Create a context
        context = {
            "title": "Test Context",
            "content": "This is a test context"
        }
        
        # Call method to test with a predictable UUID
        with patch('uuid.uuid4', return_value='new-id'):
            saved_context = self.minio_service.save_context("test-agent", context)
        
        # Verify that put_object was called with the right arguments
        self.mock_minio.put_object.assert_called_once()
        args, kwargs = self.mock_minio.put_object.call_args
        self.assertEqual(args[0], "test-bucket")  # Bucket name
        self.assertEqual(args[1], "test-agent_contexts.json")  # Object name
        
        # Verify result
        self.assertEqual(saved_context["id"], "new-id")
        self.assertEqual(saved_context["title"], "Test Context")


# Run tests if executed directly
if __name__ == '__main__':
    unittest.main()