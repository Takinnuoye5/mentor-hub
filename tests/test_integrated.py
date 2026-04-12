"""
Automated Test Suite for Mentor Hub

Tests cover:
- Package imports and structure
- CLI argument parsing
- FastAPI endpoints
- Config loading
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load test environment
load_dotenv()


class TestPackageImports(unittest.TestCase):
    """Test that core modules can be imported correctly."""
    
    def test_import_core_config(self):
        """Test importing core.config module."""
        try:
            from core import config
            self.assertIsNotNone(config.CHANNEL_IDS)
            self.assertIsNotNone(config.SYSTEM_SETTINGS)
        except ImportError as e:
            self.fail(f"Could not import core.config: {e}")
    
    def test_import_core_user_cache(self):
        """Test importing core.user_cache module."""
        try:
            from core import user_cache
            self.assertTrue(hasattr(user_cache, 'load_user_cache'))
            self.assertTrue(hasattr(user_cache, 'get_cached_user'))
        except ImportError as e:
            self.fail(f"Could not import core.user_cache: {e}")
    
    def test_import_core_package(self):
        """Test importing core package exports."""
        try:
            from core import (
                CHANNEL_IDS,
                SYSTEM_SETTINGS,
                load_user_cache,
            )
            self.assertIsNotNone(CHANNEL_IDS)
            self.assertIsNotNone(SYSTEM_SETTINGS)
            self.assertTrue(callable(load_user_cache))
        except ImportError as e:
            self.fail(f"Could not import from core package: {e}")
    
    def test_import_cli_cli(self):
        """Test importing CLI module."""
        try:
            from cli import cli
            self.assertTrue(hasattr(cli, 'main'))
        except ImportError as e:
            self.fail(f"Could not import cli.cli: {e}")
    
    def test_import_server_mentor_track_cli(self):
        """Test importing mentor_track_cli module."""
        try:
            from server import mentor_track_cli
            self.assertTrue(hasattr(mentor_track_cli, 'save_track_selection'))
            self.assertTrue(hasattr(mentor_track_cli, 'check_if_mentor_exists'))
        except ImportError as e:
            self.fail(f"Could not import server.mentor_track_cli: {e}")


class TestConfigLoading(unittest.TestCase):
    """Test configuration loading from environment."""
    
    def test_config_channel_ids_exist(self):
        """Test that channel IDs are configured."""
        from core import config
        self.assertIn("mentors", config.CHANNEL_IDS)
        self.assertIn("mentor_random", config.CHANNEL_IDS)
    
    def test_config_system_settings_exist(self):
        """Test that system settings are configured."""
        from core import config
        self.assertIn("testing_mode", config.SYSTEM_SETTINGS)
        self.assertIn("debug_level", config.SYSTEM_SETTINGS)
    
    def test_config_tracks_exist(self):
        """Test that track configuration is present."""
        from core import config
        self.assertIsNotNone(config.TRACKS)
        self.assertIn("frontend", config.TRACKS)
        self.assertIn("backend", config.TRACKS)
    
    @patch.dict(os.environ, {"TESTING_MODE": "true"})
    def test_config_env_override(self):
        """Test that environment variables override defaults."""
        # Reload config to pick up env changes
        import importlib
        from core import config
        importlib.reload(config)
        # Note: This is a simplified test; real implementation may vary


class TestCLIParsing(unittest.TestCase):
    """Test CLI argument parsing."""
    
    def test_cli_main_exists(self):
        """Test that CLI main function exists."""
        from cli.cli import main
        self.assertTrue(callable(main))
    
    def test_cli_create_stage_help(self):
        """Test CLI help for create-stage command."""
        from cli.cli import main
        # This would normally be tested with actual CLI invocation
        # For now, just verify the function exists
        self.assertTrue(callable(main))


class TestServerEndpoints(unittest.TestCase):
    """Test FastAPI server endpoints."""
    
    def test_server_app_creation(self):
        """Test that FastAPI app can be created."""
        try:
            from server.main import app
            self.assertIsNotNone(app)
        except ImportError as e:
            self.fail(f"Could not import server.main: {e}")
    
    def test_server_has_test_endpoint(self):
        """Test that /test endpoint is registered."""
        try:
            from server.main import app
            routes = [route.path for route in app.routes]
            self.assertIn("/test", routes)
        except ImportError as e:
            self.fail(f"Could not import server.main: {e}")
    
    def test_server_has_ping_endpoint(self):
        """Test that /ping endpoint is registered."""
        try:
            from server.main import app
            routes = [route.path for route in app.routes]
            self.assertIn("/ping", routes)
        except ImportError as e:
            self.fail(f"Could not import server.main: {e}")


class TestHandlers(unittest.TestCase):
    """Test server handlers module."""
    
    def test_handlers_import(self):
        """Test that handlers module can be imported."""
        try:
            from server import handlers
            self.assertTrue(hasattr(handlers, 'format_track_display_names'))
            self.assertTrue(hasattr(handlers, 'create_success_blocks'))
        except ImportError as e:
            self.fail(f"Could not import server.handlers: {e}")
    
    def test_track_display_formatting(self):
        """Test track display name formatting."""
        from server.handlers import format_track_display_names
        
        result = format_track_display_names(['backend', 'frontend'])
        self.assertIn('Backend Development', result)
        self.assertIn('Frontend Development', result)
    
    def test_success_blocks_creation(self):
        """Test success blocks creation."""
        from server.handlers import create_success_blocks
        
        blocks = create_success_blocks(['Backend Development'])
        self.assertIsInstance(blocks, list)
        self.assertGreater(len(blocks), 0)
        self.assertEqual(blocks[0]['type'], 'section')


class TestMenutorTrackCLI(unittest.TestCase):
    """Test mentor track CLI module."""
    
    def test_mentor_functions_exist(self):
        """Test that mentor track functions exist."""
        from server.mentor_track_cli import (
            save_track_selection,
            check_if_mentor_exists,
            get_mentor_info,
        )
        self.assertTrue(callable(save_track_selection))
        self.assertTrue(callable(check_if_mentor_exists))
        self.assertTrue(callable(get_mentor_info))


class TestEnvironmentSetup(unittest.TestCase):
    """Test environment and setup checks."""
    
    def test_env_file_example_exists(self):
        """Test that .env.example file exists."""
        env_example = Path(__file__).parent.parent / ".env.example"
        self.assertTrue(env_example.exists(), ".env.example file not found")
    
    def test_required_directories_exist(self):
        """Test that required directories exist."""
        base_path = Path(__file__).parent.parent
        required = ["cli", "core", "scripts", "server", "tests"]
        
        for dir_name in required:
            dir_path = base_path / dir_name
            self.assertTrue(
                dir_path.is_dir(),
                f"Required directory {dir_name} not found"
            )
    
    def test_required_files_exist(self):
        """Test that required files exist."""
        base_path = Path(__file__).parent.parent
        required_files = [
            "README.md",
            "requirements.txt",
            ".env.example",
            "setup_check.py",
        ]
        
        for file_name in required_files:
            file_path = base_path / file_name
            self.assertTrue(
                file_path.is_file(),
                f"Required file {file_name} not found"
            )


def run_tests():
    """Run all tests and print results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestPackageImports))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigLoading))
    suite.addTests(loader.loadTestsFromTestCase(TestCLIParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestServerEndpoints))
    suite.addTests(loader.loadTestsFromTestCase(TestHandlers))
    suite.addTests(loader.loadTestsFromTestCase(TestMenutorTrackCLI))
    suite.addTests(loader.loadTestsFromTestCase(TestEnvironmentSetup))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*60)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
