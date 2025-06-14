#!/usr/bin/env python
"""
Test Vault integration for Slack webhook URL retrieval
"""
import os
import sys
import asyncio

# Add the project paths to sys.path to import the modules
sys.path.append('/app')
sys.path.append('/app/_core')
sys.path.append('/app/agents/_core')

try:
    from _core.secrets import SecretsManager
    import logging
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test-vault-slack")
    
    async def test_vault_slack_retrieval():
        """Test retrieving Slack webhook URL from Vault"""
        
        print("🔐 Testing Vault Slack Webhook URL Retrieval")
        print("=" * 50)
        
        # Initialize secrets manager
        secrets_manager = SecretsManager(logger)
        
        # Test retrieving the "SLACK_KEY" key (should map to "slack" in api-keys)
        try:
            print(f"🔍 Testing SLACK_KEY pattern (should map to api-keys/slack)")
            slack_url = secrets_manager.get_secret("SLACK_KEY")
            if slack_url:
                print(f"✅ SUCCESS: Retrieved Slack webhook URL from Vault (key: SLACK_KEY)")
                print(f"🔗 URL starts with: {slack_url[:30]}...")
                print(f"📏 URL length: {len(slack_url)} characters")
                
                # Validate it looks like a Slack webhook URL
                if "hooks.slack.com" in slack_url:
                    print(f"✅ URL format validation: Looks like valid Slack webhook")
                else:
                    print(f"⚠️  URL format warning: Doesn't look like Slack webhook")
                    
                return slack_url
            else:
                print(f"❌ FAILED: No Slack webhook URL found in Vault (key: SLACK_KEY -> api-keys/slack)")
                
        except Exception as e:
            print(f"❌ ERROR: Could not retrieve Slack webhook URL with SLACK_KEY: {e}")
            
        # Also test direct "slack" key
        try:
            print(f"\n🔄 Trying direct 'slack' key retrieval...")
            slack_url = secrets_manager.get_secret("slack")
            if slack_url:
                print(f"✅ SUCCESS: Retrieved Slack webhook URL from Vault (key: slack)")
                print(f"🔗 URL starts with: {slack_url[:30]}...")
                return slack_url
            else:
                print(f"❌ FAILED: No Slack webhook URL found in Vault (key: slack)")
                
        except Exception as e:
            print(f"❌ ERROR: Could not retrieve Slack webhook URL with slack: {e}")
            
        # Test direct Vault read
        try:
            print(f"\n🔧 Testing direct Vault read from api-keys/slack...")
            vault_url = secrets_manager._read_vault_secret("api-keys", "slack")
            if vault_url:
                print(f"✅ SUCCESS: Direct Vault read worked!")
                print(f"🔗 URL starts with: {vault_url[:30]}...")
                return vault_url
            else:
                print(f"❌ FAILED: Direct Vault read returned None")
                
        except Exception as e:
            print(f"❌ ERROR: Direct Vault read failed: {e}")
            
        return None
        
    # Run the test
    result = asyncio.run(test_vault_slack_retrieval())
    
    if result:
        print(f"\n🎯 RESULT: Vault integration working - Slack notifications will be sent!")
    else:
        print(f"\n🚫 RESULT: Vault integration issue - Slack notifications will be skipped")
        
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("This test needs to run inside the Docker container with proper imports")