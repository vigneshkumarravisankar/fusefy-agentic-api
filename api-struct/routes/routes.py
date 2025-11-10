from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.adk.runners import InMemoryRunner
from google.genai import types
from agent.agent import FUSE_USECASE_AGENT
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
import asyncio
from google.adk.agents import Agent


router = APIRouter()


class Query(BaseModel):
    query_message: str


@router.get("/")
async def homepage():
    return {
        "message": "Hwllo World"
    }
    
    
@router.get("/execute-agent")
async def execute_agent():
    # params = query
    
    session_service = InMemorySessionService()

    # Define constants for identifying the interaction context
    APP_NAME = "fusefy_usecase_agentic_app"
    USER_ID = "user_1"
    SESSION_ID = "session_003" 

    # Create the specific session where the conversation will happen
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID
    )
    print(f"Session created: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")

    # --- Runner ---
    
    # Key Concept: Runner orchestrates the agent execution loop.
    runner = Runner(
        agent=FUSE_USECASE_AGENT, 
        app_name=APP_NAME,   # Associates runs with our app
        session_service=session_service # Uses our session manager
    )
    print(f"Runner created for agent '{runner.agent.name}'.")

    response = await call_agent_async("List of usecases in energy sector?" + "Strictly retrieve set of results only from the provided knowledge only, if not say \"It\'s beyond my scope, I can't fetch the relevant information for the query\"",
                                       runner=runner,
                                       user_id=USER_ID,
                                       session_id=SESSION_ID)
    
    return {"message": response}




async def call_agent_async(query: str, runner, user_id, session_id):
  """Sends a query to the agent and prints the final response."""
  print(f"\n>>> User Query: {query}")

  # Prepare the user's message in ADK format
  content = types.Content(role='user', parts=[types.Part(text=query)])

  final_response_text = "Agent did not produce a final response." # Default

  # Key Concept: run_async executes the agent logic and yields Events.
  # We iterate through events to find the final answer.
  async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
      # You can uncomment the line below to see *all* events during execution
      # print(f"  [Event] Author: {event.author}, Type: {type(event).__name__}, Final: {event.is_final_response()}, Content: {event.content}")

      # Key Concept: is_final_response() marks the concluding message for the turn.
      if event.is_final_response():
          if event.content and event.content.parts:
             # Assuming text response in the first part
             final_response_text = event.content.parts[0].text
          elif event.actions and event.actions.escalate: # Handle potential errors/escalations
             final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
          # Add more checks here if needed (e.g., specific error codes)
          break # Stop processing events once the final response is found

  print(f"<<< Agent Response: {final_response_text}")
    
