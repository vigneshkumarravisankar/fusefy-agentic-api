"""Input validation models"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, Literal

class APIRequest(BaseModel):
    """Base API request validation"""
    endpoint: str = Field(..., min_length=1, description="API endpoint path")
    method: Literal["GET", "POST", "PUT", "DELETE"] = Field(default="GET")
    resource_id: Optional[str] = Field(None, min_length=1)
    data: Optional[Dict[str, Any]] = None
    params: Optional[Dict[str, Any]] = None
    token: Optional[str] = Field(None, min_length=10)
    
    @validator('endpoint')
    def validate_endpoint(cls, v):
        if not v.startswith('/'):
            v = f"/{v}"
        return v

class ResourceOperation(BaseModel):
    """Resource management operation validation"""
    operation: Literal["list", "get", "create", "update", "delete"]
    resource_id: Optional[str] = Field(None, min_length=1)
    data: Optional[Dict[str, Any]] = None
    token: str = Field(..., min_length=10)
    
    @validator('resource_id')
    def validate_resource_id_required(cls, v, values):
        operation = values.get('operation')
        if operation in ['get', 'update', 'delete'] and not v:
            raise ValueError(f"resource_id required for {operation} operation")
        return v
    
    @validator('data')
    def validate_data_required(cls, v, values):
        operation = values.get('operation')
        if operation in ['create', 'update'] and not v:
            raise ValueError(f"data required for {operation} operation")
        return v

class EmailRequest(BaseModel):
    """Email request validation"""
    email_data: Dict[str, Any] = Field(...)
    use_aws: bool = Field(default=False)
    token: str = Field(..., min_length=10)
    
    @validator('email_data')
    def validate_email_data(cls, v):
        required_fields = ['to', 'subject', 'body']
        for field in required_fields:
            if field not in v:
                raise ValueError(f"email_data must contain '{field}'")
        return v
