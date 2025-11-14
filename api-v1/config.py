"""Configuration and shared resources"""
import aiohttp
import boto3
import json
from functools import lru_cache
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class Config:
    """Application configuration"""
    BASE_URL = "https://85tb7na8f9.execute-api.us-east-1.amazonaws.com"
    API_DOCS_URL = f"{BASE_URL}/api-docs"
    
    # Timeout settings
    CONNECT_TIMEOUT = 5
    READ_TIMEOUT = 30
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 1
    
    # Cache settings
    JWT_SECRET_CACHE_TTL = 3600  # 1 hour

class SessionManager:
    """Manages shared aiohttp session"""
    _session: Optional[aiohttp.ClientSession] = None
    
    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """Get or create shared session"""
        if cls._session is None or cls._session.closed:
            timeout = aiohttp.ClientTimeout(
                connect=Config.CONNECT_TIMEOUT,
                total=Config.READ_TIMEOUT
            )
            cls._session = aiohttp.ClientSession(timeout=timeout)
        return cls._session
    
    @classmethod
    async def close_session(cls):
        """Close shared session"""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None

@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    """Get JWT_SECRET from AWS Secrets Manager with caching"""
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
        logger.error(f"Error retrieving JWT secret: {e}")
        raise
