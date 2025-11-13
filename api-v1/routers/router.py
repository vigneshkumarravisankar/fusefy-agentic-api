from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Header
from pydantic import BaseModel
from google.adk.runners import Runner
from google.genai import types
from agent.agent import FUSE_USECASE_AGENT, execute_fusefy_tool, extract_token_from_message
from google.adk.sessions import InMemorySessionService
import asyncio
from typing import Optional
import base64
import boto3
import json
import jwt
from datetime import datetime
import jwt
from jwt import PyJWT




router = APIRouter()

def get_jwt_secret():
    """Get JWT_SECRET from AWS Secrets Manager"""
    client = boto3.client('secretsmanager', region_name='us-east-1')

    try:
        response = client.get_secret_value(SecretId='JWT_SECRET')

        if 'SecretString' in response:
            secret = response['SecretString']
            try:
                return json.loads(secret).get('JWT_SECRET', secret)
            except:
                return secret
        else:
            return response['SecretBinary']

    except Exception as e:
        print(f"Error retrieving JWT secret: {e}")
        raise

def verify_jwt_token(token: str, secret: str) -> dict:
    """Verify JWT token and return decoded payload"""
    try:
        decoded = jwt.decode(token, secret, algorithms='HS256')
        return {"valid": True, "payload": decoded}
    except Exception as e:
        return {"valid": False, "error": f"Token verification failed: {str(e)}"}

async def call_agent_async(
    query: str, 
    runner, 
    user_id, 
    session_id, 
    auth_token: str = None,
    file_data: Optional[dict] = None
):
    """Sends a query to the agent with auth token and optional file attachment."""
    print(f"\n>>> User Query: {query}")
    print(f">>> Auth Token Present: {bool(auth_token)}")

    # Inject the auth token into the query context
    if auth_token:
        query = f"{query}\n\n[AUTH_TOKEN: {auth_token}]"

    # Prepare the message parts
    parts = [types.Part(text=query)]

    # Add file if provided
    if file_data:
        print(f">>> Attached file: {file_data['filename']} ({file_data['content_type']})")

        if file_data['content_type'].startswith('image/'):
            parts.append(
                types.Part(
                    inline_data=types.Blob(
                        mime_type=file_data['content_type'],
                        data=file_data['data']
                    )
                )
            )
        elif file_data['content_type'] == 'application/pdf':
            parts.append(
                types.Part(
                    inline_data=types.Blob(
                        mime_type='application/pdf',
                        data=file_data['data']
                    )
                )
            )

    # Prepare the user's message
    content = types.Content(role='user', parts=parts)
    final_response_text = "Agent did not produce a final response."

    # Execute the agent and process events
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):

        # Handle tool calls
        if hasattr(event, 'tool_calls') and event.tool_calls:
            for tool_call in event.tool_calls:
                function_name = tool_call.function_name
                args = tool_call.args if hasattr(tool_call, 'args') else {}

                # Always inject auth token into tool args
                if auth_token and 'token' not in args:
                    args['token'] = auth_token

                print(f">>> Executing tool: {function_name}")
                print(f">>> Tool args (excluding token): {k: v for k, v in args.items() if k != 'token'}")

                try:
                    # Execute the tool with auth token
                    result = await execute_fusefy_tool(function_name, args)

                    # Parse result to check for errors
                    result_data = json.loads(result)
                    if result_data.get("status") == 401:
                        print(">>> Authentication failed in tool execution")

                    # Send tool result back to agent
                    tool_response = types.Content(
                        role='tool',
                        parts=[types.Part(
                            function_response=types.FunctionResponse(
                                name=function_name,
                                response={"result": result}
                            )
                        )]
                    )

                    # Continue the conversation with tool results
                    async for response_event in runner.run_async(
                        user_id=user_id, 
                        session_id=session_id, 
                        new_message=tool_response
                    ):
                        if response_event.is_final_response():
                            if response_event.content and response_event.content.parts:
                                final_response_text = response_event.content.parts[0].text
                            break

                except Exception as e:
                    print(f"Error executing tool {function_name}: {str(e)}")
                    error_response = types.Content(
                        role='tool',
                        parts=[types.Part(
                            function_response=types.FunctionResponse(
                                name=function_name,
                                response={"error": str(e)}
                            )
                        )]
                    )
                    async for response_event in runner.run_async(
                        user_id=user_id, 
                        session_id=session_id, 
                        new_message=error_response
                    ):
                        if response_event.is_final_response():
                            if response_event.content and response_event.content.parts:
                                final_response_text = response_event.content.parts[0].text
                            break

        # Check for final response
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
            elif event.actions and event.actions.escalate:
                final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
            break

    # Clean up the response (remove AUTH_TOKEN if it appears)
    final_response_text = extract_token_from_message(final_response_text)[0]

    print(f"<<< Agent Response: {final_response_text[:200]}...")
    return final_response_text

@router.get("/")
async def homepage():
    return {
        "message": "Fusefy Agent API - Ready",
        "version": "2.0",
        "endpoints": {
            "POST /execute-agent": "Execute agent with JWT authentication",
            "GET /execute-agent-simple": "Simple query execution with optional header auth",
            "GET /verify-token": "Verify JWT token validity",
            "POST /test-api-connection": "Test Fusefy API connection",
            "GET /list-endpoints": "List all available Fusefy endpoints"
        },
        "authentication": "JWT token required in 'token' header for API calls"
    }

@router.post("/execute-agent")
async def execute_agent(
    token: str = Form(..., description="JWT token for authentication"),
    query: str = Form(..., description="Query for the agent"),
    file: UploadFile = File(None, description="Optional file upload")
):
    """
    Execute agent with JWT authentication and optional file upload.
    The token will be automatically passed to all API calls made by the agent.
    """

    # Get JWT secret from AWS
    try:
        aws_jwt_secret = get_jwt_secret()
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to retrieve JWT secret: {str(e)}"
        )

    # Verify the provided token
    token_verification = verify_jwt_token(token, aws_jwt_secret)

    if not token_verification["valid"]:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {token_verification['error']}"
        )

    print(f"Token verified successfully for user: {token_verification['payload'].get('sub', 'unknown')}")

    # Create session
    session_service = InMemorySessionService()

    APP_NAME = "fusefy_usecase_agentic_app"
    USER_ID = token_verification['payload'].get('sub', 'user_1')
    SESSION_ID = f"session_{asyncio.get_event_loop().time()}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID
    )

    # Create runner
    runner = Runner(
        agent=FUSE_USECASE_AGENT, 
        app_name=APP_NAME,
        session_service=session_service
    )

    # Process file if provided
    file_data = None
    if file:
        try:
            content = await file.read()
            file_data = {
                'filename': file.filename,
                'content_type': file.content_type,
                'data': base64.b64encode(content).decode('utf-8')
            }
            print(f"File uploaded: {file.filename} ({len(content)} bytes)")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

    # Call agent with query, auth token, and optional file
    try:
        response = await call_agent_async(
            query=query,
            runner=runner,
            user_id=USER_ID,
            session_id=SESSION_ID,
            auth_token=token,  # Pass the verified token to the agent
            file_data=file_data
        )

        return {
            "success": True,
            "message": response,
            "user": USER_ID,
            "file_processed": file.filename if file else None,
            "authenticated": True
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution error: {str(e)}")

@router.get("/execute-agent-simple")
async def execute_agent_simple(
    query: str,
    token: Optional[str] = Header(None, description="JWT token in header")
):
    """
    Simple GET endpoint with optional JWT token in header.
    Pass token as header: token: your-jwt-token
    """

    auth_token = None
    user_id = "guest_user"

    # If token is provided, verify it
    if token:
        try:
            aws_jwt_secret = get_jwt_secret()
            token_verification = verify_jwt_token(token, aws_jwt_secret)

            if token_verification["valid"]:
                auth_token = token
                user_id = token_verification['payload'].get('sub', 'user_1')
                print(f"Authenticated request from user: {user_id}")
            else:
                return {
                    "success": False,
                    "error": f"Invalid token: {token_verification['error']}",
                    "authenticated": False
                }
        except Exception as e:
            print(f"Token verification failed: {str(e)}")
            return {
                "success": False,
                "error": f"Token verification failed: {str(e)}",
                "authenticated": False
            }
    else:
        return {
            "success": False,
            "error": "Authentication token required. Please provide a valid JWT token in the 'token' header.",
            "authenticated": False
        }

    # Create session
    session_service = InMemorySessionService()

    APP_NAME = "fusefy_usecase_agentic_app"
    SESSION_ID = f"session_{asyncio.get_event_loop().time()}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=SESSION_ID
    )

    runner = Runner(
        agent=FUSE_USECASE_AGENT, 
        app_name=APP_NAME,
        session_service=session_service
    )

    # Call agent with auth token
    try:
        response = await call_agent_async(
            query=query,
            runner=runner,
            user_id=user_id,
            session_id=SESSION_ID,
            auth_token=auth_token
        )

        return {
            "success": True,
            "message": response,
            "authenticated": True,
            "user": user_id
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Agent execution error: {str(e)}",
            "authenticated": bool(auth_token)
        }

@router.get("/verify-token")
async def verify_token(token: str = Header(..., description="JWT token to verify")):
    """
    Verify if a JWT token is valid.
    Pass token in header as: token: your-jwt-token
    """
    try:
        aws_jwt_secret = get_jwt_secret()
        verification = verify_jwt_token(token, aws_jwt_secret)

        if verification["valid"]:
            payload = verification["payload"]
            return {
                "valid": True,
                "user": payload.get("sub"),
                "expires": datetime.fromtimestamp(payload.get("exp", 0)).isoformat() if "exp" in payload else None,
                "issued": datetime.fromtimestamp(payload.get("iat", 0)).isoformat() if "iat" in payload else None
            }
        else:
            raise HTTPException(
                status_code=401,
                detail=verification["error"]
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Token verification failed: {str(e)}"
        )

@router.get("/list-endpoints")
async def list_endpoints():
    """
    List all available Fusefy API endpoints.
    No authentication required for this informational endpoint.
    """
    from tools_config import FusefyAPITools

    try:
        endpoints = await FusefyAPITools.list_available_endpoints()

        if "error" in endpoints:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch endpoints: {endpoints['error']}"
            )

        return {
            "success": True,
            "total_endpoints": endpoints.get("total_endpoints", 0),
            "base_url": endpoints.get("base_url"),
            "authentication": endpoints.get("authentication"),
            "categories": endpoints.get("categories", {})
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list endpoints: {str(e)}"
        )

@router.post("/test-api-connection")
async def test_api_connection(
    token: str = Form(..., description="JWT token for authentication"),
    endpoint: str = Form("/frameworks", description="Endpoint to test")
):
    """
    Test the connection to a specific Fusefy API endpoint with the provided token.
    """

    # Verify token first
    try:
        aws_jwt_secret = get_jwt_secret()
        token_verification = verify_jwt_token(token, aws_jwt_secret)

        if not token_verification["valid"]:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: {token_verification['error']}"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Token verification failed: {str(e)}"
        )

    # Test API connection
    from tools_config import FusefyAPITools

    try:
        # Test the specified endpoint
        test_result = await FusefyAPITools.call_fusefy_api(
            endpoint=endpoint,
            method="GET",
            token=token
        )

        return {
            "success": True,
            "endpoint_tested": endpoint,
            "api_call_success": test_result.get("success", False),
            "status_code": test_result.get("status"),
            "authenticated": test_result.get("status") != 401,
            "message": "API connection successful" if test_result.get("success") else f"API call failed with status {test_result.get('status')}",
            "data_preview": test_result.get("data", {}) if test_result.get("success") else None
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"API connection test failed: {str(e)}"
        )