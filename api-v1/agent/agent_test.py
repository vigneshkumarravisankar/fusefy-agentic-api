# test_runner.py
from google.adk.runners import Runner
from google.adk.agents import Agent
import inspect

# Check what Runner expects
print("Runner __init__ signature:")
print(inspect.signature(Runner.__init__))

# Check what Agent class looks like
print("\nAgent __init__ signature:")
print(inspect.signature(Agent.__init__))

# Try to find BaseAgent
try:
    from google.adk.agents import BaseAgent
    print("\nBaseAgent found!")
    print("BaseAgent __init__ signature:")
    print(inspect.signature(BaseAgent.__init__))
except ImportError:
    print("\nBaseAgent not found")

# Check for other agent types
try:
    from google.adk.agents import SimpleAgent
    print("\nSimpleAgent found!")
except ImportError:
    print("\nSimpleAgent not found")