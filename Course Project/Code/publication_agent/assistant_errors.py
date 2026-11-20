"""Safe client-facing errors; never expose provider organization/billing payloads."""
class AssistantServiceError(RuntimeError):
    def __init__(self,message,status_code=503,retry_after=None):
        super().__init__(message);self.status_code=status_code;self.retry_after=retry_after

def provider_error(exc):
    text=str(exc).lower();status=getattr(exc,'status_code',None) or getattr(exc,'code',None)
    if not isinstance(status,int):status=None
    if status==429 or 'resource_exhausted' in text or 'rate limit' in text or 'rate_limit' in text or 'error code: 429' in text:
        return AssistantServiceError('The AI request limit was reached. Wait a moment and try again, or ask a shorter question. Local dashboard controls still work.',429,5)
    if status in {401,403}:
        return AssistantServiceError('Gemini rejected the configured credentials or model access. Ask an administrator to check Configure AI.',503)
    if status and status>=500:
        return AssistantServiceError('The AI provider is temporarily unavailable. Try again shortly.',503,5)
    return None
