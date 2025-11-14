from fastapi import APIRouter, Request, HTTPException, File, UploadFile, Form, Header
from pydantic import BaseModel
from google.adk.runners import Runner
from google.genai import types
from agent.agent import FUSE_USECASE_AGENT, extract_token_from_message
from tools_config import FusefyAPITools, FUSEFY_API_TOOLS
from google.adk.sessions import InMemorySessionService
import asyncio
import logging
from typing import Optional
import base64
import json
import jwt
from datetime import datetime
from config import get_jwt_secret

logger = logging.getLogger(__name__)
router = APIRouter()


class ExecuteAgentRequest(BaseModel):
    token: str
    query: str
    session_id: Optional[str] = None
    file: Optional[dict] = None


def verify_jwt_token(token: str, secret: str) -> dict:
    """Verify JWT token and return decoded payload"""
    try:
        decoded = jwt.decode(token, secret, algorithms='HS256')
        return {"valid": True, "payload": decoded}
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
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
    logger.info(f"User Query: {query[:100]}...")
    logger.debug(f"Auth Token Present: {bool(auth_token)}")

    # Inject the auth token into the query context
    if auth_token:
        query = f"{query}\n\n[AUTH_TOKEN: {auth_token}]"

    # Prepare the message parts
    parts = [types.Part(text=query)]

    # Add file if provided
    if file_data:
        logger.info(f"Attached file: {file_data['filename']} ({file_data['content_type']})")

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

                logger.info(f"Executing tool: {function_name}")
                logger.debug(f"Tool args (excluding token): {dict((k, v) for k, v in args.items() if k != 'token')}")

                try:
                    # Execute the tool by calling FusefyAPITools directly
                    if hasattr(FusefyAPITools, function_name):
                        func = getattr(FusefyAPITools, function_name)
                        result = await func(**args)
                    else:
                        result = {"error": f"Function {function_name} not found"}

                    # Check for authentication errors
                    if isinstance(result, dict) and result.get("status") == 401:
                        logger.warning("Authentication failed in tool execution")

                    # Send tool result back to agent
                    tool_response = types.Content(
                        role='tool',
                        parts=[types.Part(
                            function_response=types.FunctionResponse(
                                name=function_name,
                                response=result
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
                    logger.error(f"Error executing tool {function_name}: {str(e)}")
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

    logger.info(f"Agent Response: {final_response_text[:200]}...")
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

# @router.post("/execute-agent")
# async def execute_agent(
#     token: str = Form(..., description="JWT token for authentication"),
#     query: str = Form(..., description="Query for the agent"),
#     session_id: Optional[str] = Form(None, description="Session ID from frontend"),
#     file: UploadFile = File(None, description="Optional file upload")
# ):
#     """
#     Execute agent with JWT authentication and optional file upload.
#     The token will be automatically passed to all API calls made by the agent.
#     Files are automatically analyzed by the LLM based on their type.
#     """

#     # Get JWT secret from AWS (cached)
#     try:
#         aws_jwt_secret = get_jwt_secret()
#     except Exception as e:
#         logger.error(f"Failed to retrieve JWT secret: {str(e)}")
#         raise HTTPException(
#             status_code=500, 
#             detail=f"Failed to retrieve JWT secret: {str(e)}"
#         )

#     # Verify the provided token
#     token_verification = verify_jwt_token(token, aws_jwt_secret)

#     if not token_verification["valid"]:
#         raise HTTPException(
#             status_code=401,
#             detail=f"Invalid token: {token_verification['error']}"
#         )

#     logger.info(f"Token verified successfully for user: {token_verification['payload'].get('sub', 'unknown')}")

#     # Create session
#     session_service = InMemorySessionService()

#     APP_NAME = "fusefy_usecase_agentic_app"
#     USER_ID = token_verification['payload'].get('sub', 'user_1')
#     SESSION_ID = session_id if session_id else f"session_{asyncio.get_event_loop().time()}"

#     session = await session_service.create_session(
#         app_name=APP_NAME,
#         user_id=USER_ID,
#         session_id=SESSION_ID
#     )

#     # Create runner
#     runner = Runner(
#         agent=FUSE_USECASE_AGENT, 
#         app_name=APP_NAME,
#         session_service=session_service
#     )

#     # Process file if provided - LLM will automatically analyze it
#     file_data = None
#     if file:
#         try:
#             content = await file.read()
#             file_data = {
#                 'filename': file.filename,
#                 'content_type': file.content_type,
#                 'data': base64.b64encode(content).decode('utf-8')
#             }
#             logger.info(f"File uploaded for analysis: {file.filename} ({len(content)} bytes, type: {file.content_type})")
            
#             # Enhance query to trigger automatic analysis if not explicitly mentioned
#             if file and not any(word in query.lower() for word in ['analyze', 'review', 'check', 'examine', 'look']):
#                 query = f"Analyze the uploaded file '{file.filename}'. {query}"
#         except Exception as e:
#             raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

#     # Call agent with query, auth token, and optional file
#     try:
#         response = await call_agent_async(
#             query=query,
#             runner=runner,
#             user_id=USER_ID,
#             session_id=SESSION_ID,
#             auth_token=token,  # Pass the verified token to the agent
#             file_data=file_data
#         )

#         return {
#             "success": True,
#             "message": response,
#             "user": USER_ID,
#             "session_id": SESSION_ID,
#             "file_processed": file.filename if file else None,
#             "authenticated": True
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Agent execution error: {str(e)}")

@router.post("/execute-agent")
async def execute_agent(
    request: Request,
    token: Optional[str] = Form(None),
    query: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    file: UploadFile = File(None)
):
    """
    Execute agent with JWT authentication. Supports both JSON and form data.
    """
    
    # Handle JSON request
    if request.headers.get("content-type") == "application/json":
        try:
            json_data = await request.json()
            token = json_data.get("token")
            query = json_data.get("query")
            session_id = json_data.get("session_id")
            file = None  # JSON requests don't support file uploads
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Validate required fields
    if not token or not query:
        raise HTTPException(status_code=400, detail="token and query are required")

    # Get JWT secret from AWS (cached)
    try:
        aws_jwt_secret = get_jwt_secret()
    except Exception as e:
        logger.error(f"Failed to retrieve JWT secret: {str(e)}")
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

    logger.info(f"Token verified successfully for user: {token_verification['payload'].get('sub', 'unknown')}")

    # Create session
    session_service = InMemorySessionService()

    APP_NAME = "fusefy_usecase_agentic_app"
    USER_ID = token_verification['payload'].get('sub', 'user_1')
    SESSION_ID = session_id if session_id else f"session_{asyncio.get_event_loop().time()}"

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

    # Process file if provided (only for form data)
    file_data = None
    if file:
        try:
            content = await file.read()
            file_data = {
                'filename': file.filename,
                'content_type': file.content_type,
                'data': base64.b64encode(content).decode('utf-8')
            }
            logger.info(f"File uploaded for analysis: {file.filename} ({len(content)} bytes, type: {file.content_type})")
            
            if not any(word in query.lower() for word in ['analyze', 'review', 'check', 'examine', 'look']):
                query = f"Analyze the uploaded file '{file.filename}'. {query}"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

    # Call agent
    try:
        response = await call_agent_async(
            query=query,
            runner=runner,
            user_id=USER_ID,
            session_id=SESSION_ID,
            auth_token=token,
            file_data=file_data
        )

        return {
            "success": True,
            "message": response,
            "user": USER_ID,
            "session_id": SESSION_ID,
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
                logger.info(f"Authenticated request from user: {user_id}")
            else:
                return {
                    "success": False,
                    "error": f"Invalid token: {token_verification['error']}",
                    "authenticated": False
                }
        except Exception as e:
            logger.error(f"Token verification failed: {str(e)}")
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
        logger.error(f"Failed to list endpoints: {str(e)}")
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