from google.genai import types
import aiohttp
import json
from typing import Dict, Any, Optional, List
from enum import Enum

class FusefyAPITools:
    """API Tools for interacting with Fusefy API"""

    BASE_URL = "https://85tb7na8f9.execute-api.us-east-1.amazonaws.com"
    API_DOCS_URL = f"{BASE_URL}/api-docs"

    @staticmethod
    async def call_fusefy_api(
        endpoint: str, 
        method: str = "GET", 
        data: Optional[Dict[str, Any]] = None, 
        params: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
        resource_id: Optional[str] = None
    ):
        """
        Universal Fusefy API caller with JWT authentication

        Args:
            endpoint: The API endpoint path
            method: HTTP method (GET, POST, PUT, DELETE)
            data: Request body for POST/PUT
            params: Query parameters
            token: JWT authentication token (required for most endpoints)
            resource_id: ID for specific resource operations
        """
        # Build the URL
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"

        # Add resource ID to path if provided
        if resource_id and method in ["GET", "PUT", "DELETE"]:
            # Remove trailing slash if present
            endpoint = endpoint.rstrip('/')
            endpoint = f"{endpoint}/{resource_id}"

        url = f"{FusefyAPITools.BASE_URL}{endpoint}"

        # Prepare headers - IMPORTANT: Fusefy uses 'token' header, not 'Authorization'
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Add authentication token to headers
        if token:
            headers["token"] = token  # Fusefy expects token in 'token' header
            print(f"   Adding token to headers for {endpoint}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method.upper(),
                    url=url,
                    json=data,
                    params=params,
                    headers=headers
                ) as response:
                    response_text = await response.text()

                    try:
                        response_data = json.loads(response_text) if response_text else {}
                    except json.JSONDecodeError:
                        response_data = {"raw_response": response_text}

                    result = {
                        "status": response.status,
                        "data": response_data,
                        "success": 200 <= response.status < 300,
                        "endpoint": endpoint,
                        "method": method
                    }

                    if response.status == 401:
                        result["error"] = "Authentication failed. Please provide a valid JWT token."
                    elif response.status >= 400:
                        result["error"] = f"API error: {response.status}"

                    return result

        except Exception as e:
            return {
                "status": 500,
                "error": str(e),
                "success": False,
                "endpoint": endpoint,
                "method": method
            }

    @staticmethod
    async def get_api_documentation():
        """Get the complete API documentation"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(FusefyAPITools.API_DOCS_URL) as response:
                    if response.status == 200:
                        return await response.json()
                    return {"error": f"Failed to fetch API docs: {response.status}"}
        except Exception as e:
            return {"error": f"Error fetching API documentation: {str(e)}"}

    @staticmethod
    async def list_available_endpoints():
        """List all available API endpoints with their operations"""
        docs = await FusefyAPITools.get_api_documentation()

        if "error" in docs:
            return docs

        endpoints_summary = []
        paths = docs.get("paths", {})

        # Group endpoints by category
        categories = {}

        for path, methods in paths.items():
            # Extract category from tag or path
            category = "general"
            for method, details in methods.items():
                if method in ["get", "post", "put", "delete"]:
                    tags = details.get("tags", [])
                    if tags:
                        category = tags[0]
                    break

            if category not in categories:
                categories[category] = []

            endpoint_info = {
                "path": path,
                "operations": []
            }

            for method, details in methods.items():
                if method in ["get", "post", "put", "delete"]:
                    operation = {
                        "method": method.upper(),
                        "summary": details.get("summary", ""),
                        "description": details.get("description", ""),
                        "requires_auth": bool(details.get("security", [])),
                        "parameters": [p.get("name") for p in details.get("parameters", [])],
                        "requires_body": bool(details.get("requestBody"))
                    }
                    endpoint_info["operations"].append(operation)

            if endpoint_info["operations"]:
                categories[category].append(endpoint_info)

        return {
            "total_endpoints": sum(len(eps) for eps in categories.values()),
            "categories": categories,
            "base_url": FusefyAPITools.BASE_URL,
            "authentication": "JWT token required in 'token' header"
        }

# Define comprehensive tools for Google ADK
FUSEFY_API_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="call_fusefy_api",
                description="Call any Fusefy API endpoint with JWT authentication in header",
                parameters={
                    "type": "object",
                    "properties": {
                        "endpoint": {
                            "type": "string",
                            "description": "API endpoint path (e.g., /frameworks, /controls, /assessments, /usecase, /tenant, /documents)"
                        },
                        "method": {
                            "type": "string",
                            "enum": ["GET", "POST", "PUT", "DELETE"],
                            "description": "HTTP method to use"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Optional resource ID for GET/PUT/DELETE operations on specific items"
                        },
                        "data": {
                            "type": "object",
                            "description": "Request body data for POST/PUT operations"
                        },
                        "params": {
                            "type": "object",
                            "description": "Query parameters for GET requests"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token (required for authenticated endpoints)"
                        }
                    },
                    "required": ["endpoint", "method"]
                }
            ),
            types.FunctionDeclaration(
                name="list_available_endpoints",
                description="Get a categorized list of all available Fusefy API endpoints",
                parameters={
                    "type": "object",
                    "properties": {}
                }
            ),
            types.FunctionDeclaration(
                name="manage_frameworks",
                description="Manage frameworks in Fusefy",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "framework_id": {
                            "type": "string",
                            "description": "Framework ID (required for get/update/delete)"
                        },
                        "data": {
                            "type": "object",
                            "description": "Framework data (required for create/update)"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="manage_controls",
                description="Manage controls in Fusefy",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "control_id": {
                            "type": "string",
                            "description": "Control ID (required for get/update/delete)"
                        },
                        "data": {
                            "type": "object",
                            "description": "Control data (required for create/update)"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="manage_assessments",
                description="Create, read, update or delete assessments",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "assessment_id": {
                            "type": "string",
                            "description": "Assessment ID (required for get/update/delete)"
                        },
                        "data": {
                            "type": "object",
                            "description": "Assessment data (required for create/update)"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="manage_usecases",
                description="Manage use cases in Fusefy",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "usecase_id": {
                            "type": "string",
                            "description": "Use case ID (for specific operations)"
                        },
                        "data": {
                            "type": "object",
                            "description": "Use case data for create/update"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="manage_tenant",
                description="Manage tenant information",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant ID (for specific operations)"
                        },
                        "data": {
                            "type": "object",
                            "description": "Tenant data for create/update"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="manage_documents",
                description="Manage documents and policy documents",
                parameters={
                    "type": "object",
                    "properties": {
                        "document_type": {
                            "type": "string",
                            "enum": ["documents", "policyDocuments"],
                            "description": "Type of document to manage"
                        },
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "document_id": {
                            "type": "string",
                            "description": "Document ID (for specific operations)"
                        },
                        "data": {
                            "type": "object",
                            "description": "Document data for create/update"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["document_type", "operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="manage_cloud_resources",
                description="Manage cloud resources (AWS S3, Azure Blob, Lambda, Cloud Providers)",
                parameters={
                    "type": "object",
                    "properties": {
                        "resource_type": {
                            "type": "string",
                            "enum": ["awsS3", "azureBlob", "lambda", "cloudProviders", "cloudFrameworks"],
                            "description": "Type of cloud resource"
                        },
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID (for specific operations)"
                        },
                        "data": {
                            "type": "object",
                            "description": "Resource data for create/update"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["resource_type", "operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="send_email",
                description="Send email using Fusefy's email service",
                parameters={
                    "type": "object",
                    "properties": {
                        "email_data": {
                            "type": "object",
                            "description": "Email data including recipient, subject, body"
                        },
                        "use_aws": {
                            "type": "boolean",
                            "description": "Use AWS Simple Email Service if true, otherwise use standard email"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["email_data", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="get_metrics_and_insights",
                description="Get methodology metrics, TCO, adoption insights, or model validation data",
                parameters={
                    "type": "object",
                    "properties": {
                        "metric_type": {
                            "type": "string",
                            "enum": ["methodologyMetrics", "tco", "adoptionInsights", "modelValidation"],
                            "description": "Type of metric or insight to retrieve"
                        },
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID (for specific operations)"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update operations"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["metric_type", "operation", "token"]
                }
            )
        ]
    )
]