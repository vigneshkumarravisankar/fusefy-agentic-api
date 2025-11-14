from google.genai import types
import aiohttp
import json
import logging
from typing import Dict, Any, Optional, List
from enum import Enum
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import Config, SessionManager
from validators import APIRequest, ResourceOperation

logger = logging.getLogger(__name__)

class FusefyAPITools:
    """API Tools for interacting with Fusefy API with retry logic and connection pooling"""

    BASE_URL = Config.BASE_URL
    API_DOCS_URL = Config.API_DOCS_URL

    @staticmethod
    @retry(
        stop=stop_after_attempt(Config.MAX_RETRIES),
        wait=wait_exponential(multiplier=Config.RETRY_DELAY, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True
    )
    async def call_fusefy_api(
        endpoint: str, 
        method: str = "GET", 
        data: Optional[Dict[str, Any]] = None, 
        params: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
        resource_id: Optional[str] = None
    ):
        """
        Universal Fusefy API caller with JWT authentication, retry logic, and connection pooling

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
            endpoint = endpoint.rstrip('/')
            endpoint = f"{endpoint}/{resource_id}"

        url = f"{FusefyAPITools.BASE_URL}{endpoint}"

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        if token:
            headers["token"] = token
            logger.debug(f"Adding token to headers for {endpoint}")

        try:
            session = await SessionManager.get_session()
            
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
                    logger.warning(f"Authentication failed for {endpoint}")
                elif response.status >= 400:
                    result["error"] = f"API error: {response.status}"
                    logger.error(f"API error {response.status} for {endpoint}: {response_data}")
                else:
                    logger.info(f"Successful {method} request to {endpoint}")

                return result

        except (aiohttp.ClientError, TimeoutError) as e:
            logger.error(f"Network error calling {endpoint}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling {endpoint}: {str(e)}")
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
            session = await SessionManager.get_session()
            async with session.get(FusefyAPITools.API_DOCS_URL) as response:
                if response.status == 200:
                    return await response.json()
                return {"error": f"Failed to fetch API docs: {response.status}"}
        except Exception as e:
            logger.error(f"Error fetching API documentation: {str(e)}")
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

    @staticmethod
    async def _manage_resource(endpoint: str, operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Generic resource management - DRY principle"""
        method_map = {"list": "GET", "get": "GET", "create": "POST", "update": "PUT", "delete": "DELETE"}
        method = method_map.get(operation, "GET")
        return await FusefyAPITools.call_fusefy_api(
            endpoint=endpoint,
            method=method,
            resource_id=resource_id if operation in ["get", "update", "delete"] else None,
            data=data,
            token=token
        )

    @staticmethod
    async def manage_frameworks(operation: str, framework_id: str = None, data: dict = None, token: str = None):
        """Manage frameworks"""
        return await FusefyAPITools._manage_resource("/frameworks", operation, framework_id, data, token)

    @staticmethod
    async def manage_controls(operation: str, control_id: str = None, data: dict = None, token: str = None):
        """Manage controls"""
        return await FusefyAPITools._manage_resource("/controls", operation, control_id, data, token)

    @staticmethod
    async def manage_assessments(operation: str, assessment_id: str = None, data: dict = None, token: str = None):
        """Manage assessments"""
        return await FusefyAPITools._manage_resource("/assessments", operation, assessment_id, data, token)

    @staticmethod
    async def manage_usecases(operation: str, usecase_id: str = None, data: dict = None, token: str = None):
        """Manage use cases"""
        return await FusefyAPITools._manage_resource("/usecase", operation, usecase_id, data, token)

    @staticmethod
    async def manage_tenant(operation: str, tenant_id: str = None, data: dict = None, token: str = None):
        """Manage tenant information"""
        return await FusefyAPITools._manage_resource("/tenant", operation, tenant_id, data, token)

    @staticmethod
    async def manage_documents(operation: str, document_id: str = None, data: dict = None, token: str = None):
        """Manage documents"""
        return await FusefyAPITools._manage_resource("/documents", operation, document_id, data, token)

    @staticmethod
    async def manage_policy_documents(operation: str, document_id: str = None, data: dict = None, token: str = None):
        """Manage policy documents"""
        return await FusefyAPITools._manage_resource("/policyDocuments", operation, document_id, data, token)

    @staticmethod
    async def manage_aws_s3(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage AWS S3 resources"""
        return await FusefyAPITools._manage_resource("/awsS3", operation, resource_id, data, token)

    @staticmethod
    async def manage_azure_blob(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage Azure Blob resources"""
        return await FusefyAPITools._manage_resource("/azureBlob", operation, resource_id, data, token)

    @staticmethod
    async def manage_lambda(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage Lambda functions"""
        return await FusefyAPITools._manage_resource("/lambda", operation, resource_id, data, token)

    @staticmethod
    async def manage_cloud_providers(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage cloud providers"""
        return await FusefyAPITools._manage_resource("/cloudProviders", operation, resource_id, data, token)

    @staticmethod
    async def manage_cloud_frameworks(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage cloud frameworks"""
        return await FusefyAPITools._manage_resource("/cloudFrameworks", operation, resource_id, data, token)

    @staticmethod
    async def send_email(email_data: dict, use_aws: bool = False, token: str = None):
        """Send email"""
        endpoint = "/aws-simple-email" if use_aws else "/send-email"
        return await FusefyAPITools.call_fusefy_api(
            endpoint=endpoint,
            method="POST",
            data=email_data,
            token=token
        )

    @staticmethod
    async def manage_methodology_metrics(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage methodology metrics"""
        return await FusefyAPITools._manage_resource("/methodologyMetrics", operation, resource_id, data, token)

    @staticmethod
    async def manage_tco(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage TCO data"""
        return await FusefyAPITools._manage_resource("/tco", operation, resource_id, data, token)

    @staticmethod
    async def manage_adoption_insights(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage adoption insights"""
        return await FusefyAPITools._manage_resource("/adoptionInsights", operation, resource_id, data, token)

    @staticmethod
    async def manage_model_validation(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage model validation"""
        return await FusefyAPITools._manage_resource("/modelValidation", operation, resource_id, data, token)

    @staticmethod
    async def manage_tenant_details(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage tenant details"""
        return await FusefyAPITools._manage_resource("/tenantDetails", operation, resource_id, data, token)

    @staticmethod
    async def manage_usecase_assessment(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage usecase assessments"""
        return await FusefyAPITools._manage_resource("/usecaseAssessment", operation, resource_id, data, token)

    @staticmethod
    async def manage_features(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage features"""
        return await FusefyAPITools._manage_resource("/feature", operation, resource_id, data, token)

    @staticmethod
    async def manage_grading_types(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage grading types"""
        return await FusefyAPITools._manage_resource("/grading-types", operation, resource_id, data, token)

    @staticmethod
    async def manage_app_metadata(operation: str, resource_id: str = None, data: dict = None, token: str = None):
        """Manage app metadata"""
        return await FusefyAPITools._manage_resource("/app-metadata", operation, resource_id, data, token)

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
                description="Manage documents",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "document_id": {
                            "type": "string",
                            "description": "Document ID (for get/update/delete)"
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
                    "required": ["operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="manage_policy_documents",
                description="Manage policy documents",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "document_id": {
                            "type": "string",
                            "description": "Document ID (for get/update/delete)"
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
                    "required": ["operation", "token"]
                }
            ),
            types.FunctionDeclaration(
                name="manage_aws_s3",
                description="Manage AWS S3 resources",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Resource data"
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
                name="manage_azure_blob",
                description="Manage Azure Blob storage",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Resource data"
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
                name="manage_lambda",
                description="Manage AWS Lambda functions",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Resource data"
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
                name="manage_cloud_providers",
                description="Manage cloud providers",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Resource data"
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
                name="manage_cloud_frameworks",
                description="Manage cloud frameworks",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Resource data"
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
                name="manage_methodology_metrics",
                description="Manage methodology metrics",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
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
                name="manage_tco",
                description="Manage TCO (Total Cost of Ownership) data",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
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
                name="manage_adoption_insights",
                description="Manage adoption insights",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
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
                name="manage_model_validation",
                description="Manage model validation data",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
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
                name="manage_tenant_details",
                description="Manage tenant details",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
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
                name="manage_usecase_assessment",
                description="Manage usecase assessments",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
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
                name="manage_features",
                description="Manage features",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
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
                name="manage_grading_types",
                description="Manage grading types",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
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
                name="manage_app_metadata",
                description="Manage app metadata",
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["list", "get", "create", "update", "delete"],
                            "description": "Operation to perform"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID"
                        },
                        "data": {
                            "type": "object",
                            "description": "Data for create/update"
                        },
                        "token": {
                            "type": "string",
                            "description": "JWT authentication token"
                        }
                    },
                    "required": ["operation", "token"]
                }
            )
        ]
    )
]