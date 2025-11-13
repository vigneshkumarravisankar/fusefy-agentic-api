from google.adk.agents import Agent
from google.genai import types
from tools_config import FUSEFY_API_TOOLS, FusefyAPITools
import json
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import os
from google.adk.models.lite_llm import LiteLlm

load_dotenv()

openai_key = os.getenv("OPENAI_API_KEY")

# Helper function to extract token from message
def extract_token_from_message(message: str) -> tuple[str, str]:
    """Extract AUTH_TOKEN from message and return cleaned message and token"""
    token_pattern = r'\[AUTH_TOKEN:\s*([^\]]+)\]'
    match = re.search(token_pattern, message)

    if match:
        token = match.group(1).strip()
        cleaned_message = re.sub(token_pattern, '', message).strip()
        return cleaned_message, token

    return message, None

# Simplified tool executor - let the LLM handle function selection
async def execute_fusefy_tool(function_call: dict):
    """
    Execute Fusefy API tools based on LLM's function call decision

    Args:
        function_call: Dictionary containing 'name' and 'arguments' from LLM
    """
    try:
        function_name = function_call.get("name")
        args = function_call.get("arguments", {})

        # Ensure token is present
        token = args.get("token")
        if not token:
            return {
                "error": "Authentication token is required. Please provide a valid JWT token.",
                "status": 401
            }

        # Get the actual function from FusefyAPITools
        if hasattr(FusefyAPITools, function_name):
            func = getattr(FusefyAPITools, function_name)
            result = await func(**args)
            return result
        else:
            return {"error": f"Function {function_name} not found in FusefyAPITools"}

    except Exception as e:
        return {"error": f"Tool execution error: {str(e)}"}

# System prompt for the agent
SYSTEM_PROMPT = """You are the Fusefy API Assistant, specialized in helping users interact with the comprehensive Fusefy platform.

AUTHENTICATION: All API calls require a JWT token. When you see [AUTH_TOKEN: ...] in the message, extract and use that token for all API calls.

## Your Capabilities:
- Manage frameworks, controls, assessments, and use cases
- Handle cloud resources (AWS S3, Azure Blob, Lambda)
- Provide analytics and insights (metrics, TCO, adoption insights)
- Manage tenants and users
- Handle documents and policies
- Send emails via standard or AWS SES
- Perform CRUD operations on all resources

## Important Guidelines:
1. Always extract and use the JWT token from [AUTH_TOKEN: ...] format
2. Choose the appropriate function based on user's request
3. Handle errors gracefully and provide helpful feedback
4. Present data in a clear, organized format
5. Explain what each operation does when asked

You have access to various functions that the system will automatically route based on your selection."""

# Define the tools/functions for the LLM to use
# This should match your actual FusefyAPITools methods
FUSEFY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "call_fusefy_api",
            "description": "Make a direct API call to any Fusefy endpoint",
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "API endpoint path (e.g., /frameworks, /controls)"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                        "description": "HTTP method"
                    },
                    "resource_id": {
                        "type": "string",
                        "description": "Optional resource ID for specific resource operations"
                    },
                    "data": {
                        "type": "object",
                        "description": "Request body data for POST/PUT requests"
                    },
                    "params": {
                        "type": "object",
                        "description": "Query parameters"
                    },
                    "token": {
                        "type": "string",
                        "description": "JWT authentication token"
                    }
                },
                "required": ["endpoint", "method", "token"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_endpoints",
            "description": "List all available Fusefy API endpoints",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_frameworks",
            "description": "Manage compliance and security frameworks",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["list", "get", "create", "update", "delete"],
                        "description": "Operation to perform"
                    },
                    "framework_id": {
                        "type": "string",
                        "description": "Framework ID for get/update/delete operations"
                    },
                    "data": {
                        "type": "object",
                        "description": "Framework data for create/update operations"
                    },
                    "token": {
                        "type": "string",
                        "description": "JWT authentication token"
                    }
                },
                "required": ["operation", "token"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_controls",
            "description": "Manage security and compliance controls",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["list", "get", "create", "update", "delete"],
                        "description": "Operation to perform"
                    },
                    "control_id": {
                        "type": "string",
                        "description": "Control ID for get/update/delete operations"
                    },
                    "data": {
                        "type": "object",
                        "description": "Control data for create/update operations"
                    },
                    "token": {
                        "type": "string",
                        "description": "JWT authentication token"
                    }
                },
                "required": ["operation", "token"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send email via standard service or AWS SES",
            "parameters": {
                "type": "object",
                "properties": {
                    "email_data": {
                        "type": "object",
                        "description": "Email data including to, subject, body",
                        "properties": {
                            "to": {"type": "string"},
                            "subject": {"type": "string"},
                            "body": {"type": "string"},
                            "from": {"type": "string"}
                        }
                    },
                    "use_aws": {
                        "type": "boolean",
                        "description": "Use AWS SES if true, standard email if false"
                    },
                    "token": {
                        "type": "string",
                        "description": "JWT authentication token"
                    }
                },
                "required": ["email_data", "token"]
            }
        }
    }
    # Add more function definitions as needed
]

# Create the agent with simplified configuration
# try:
    # Using LiteLLM with OpenAI
FUSE_USECASE_AGENT = Agent(
        name="fusefy_agent",
        model=LiteLlm(model="openai/gpt-4o"),
        instruction=SYSTEM_PROMPT,
        tools=[execute_fusefy_tool],  # Pass the function definitions  
    )
print("Successfully created Fusefy Agent with LiteLLM")


# Export the agent
__all__ = ['FUSE_USECASE_AGENT', 'extract_token_from_message']