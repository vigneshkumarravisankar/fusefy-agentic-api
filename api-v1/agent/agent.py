from google.adk.agents import Agent
from google.genai import types
from tools_config import FUSEFY_API_TOOLS, FusefyAPITools
import json
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import os
import re
import json
from google.adk.models.lite_llm import LiteLlm
from google.adk import Agent
from tools_config import FusefyAPITools, FUSEFY_API_TOOLS

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

# Tool executor that routes to FusefyAPITools
async def execute_fusefy_tool(function_name: str, args: Optional[Dict] = None):
    """
    Execute Fusefy API tools based on function name and arguments

    Args:
        function_name: Name of the function to execute
        args: Dictionary of arguments to pass to the function
    """
    try:
        if args is None:
            args = {}

        # Get the actual function from FusefyAPITools
        if hasattr(FusefyAPITools, function_name):
            func = getattr(FusefyAPITools, function_name)
            result = await func(**args)
            return result
        else:
            return {"error": f"Function {function_name} not found in FusefyAPITools"}

    except Exception as e:
        return {"error": f"Tool execution error: {str(e)}", "function": function_name}

# System prompt for the agent
SYSTEM_PROMPT = """You are the Fusefy API Assistant for the Fusefy compliance and security platform.

AUTHENTICATION: All API calls require a JWT token in the 'token' header. Extract from [AUTH_TOKEN: ...] and pass to all functions.

## Available Resources (all support list/get/create/update/delete):
- Frameworks & Controls: manage_frameworks, manage_controls
- Assessments: manage_assessments, manage_usecases, manage_usecase_assessment
- Tenant: manage_tenant, manage_tenant_details
- Documents: manage_documents, manage_policy_documents
- Cloud: manage_aws_s3, manage_azure_blob, manage_lambda, manage_cloud_providers, manage_cloud_frameworks
- Metrics: manage_methodology_metrics, manage_tco, manage_adoption_insights, manage_model_validation
- Other: manage_features, manage_grading_types, manage_app_metadata
- Email: send_email (use_aws=True for AWS SES)
- General: call_fusefy_api (direct endpoint access), list_available_endpoints

## Guidelines:
1. Always pass JWT token to all function calls
2. For file uploads: automatically analyze based on type
3. Use call_fusefy_api for endpoints not covered by specific functions
4. Present data clearly, handle errors gracefully

API: https://85tb7na8f9.execute-api.us-east-1.amazonaws.com"""



# Create the agent - tools handled manually in router
FUSE_USECASE_AGENT = Agent(
    name="fusefy_agent",
    model=LiteLlm(model="openai/gpt-4o"),
    instruction=SYSTEM_PROMPT
)
print("Successfully created Fusefy Agent with LiteLLM")


# Export the agent
__all__ = ['FUSE_USECASE_AGENT', 'extract_token_from_message']