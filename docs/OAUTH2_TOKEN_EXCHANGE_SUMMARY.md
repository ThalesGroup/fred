# OAuth2 Token Exchange Implementation Summary

## 🎯 Problem Solved

When user `alice` creates resources via MCP calls in Fred, the `author` field was showing "service-account-agentic" instead of alice's unique identifier (`sub` field from JWT). This was because the Agentic backend was using service account tokens for all MCP calls to Knowledge Flow backend.

## ✅ Solution Implemented

**OAuth2 Token Exchange (RFC 8693)** to preserve user identity in service-to-service calls.

### Architecture Flow

1. **User Authentication**: alice logs in via frontend → gets JWT token with `sub` field
2. **Token Propagation**: Frontend sends JWT token via WebSocket auth message
3. **Token Storage**: Agentic backend stores user token in RuntimeContext
4. **Token Exchange**: When making MCP calls, user token is exchanged for service token that preserves alice's identity (`sub` field)
5. **Resource Creation**: Knowledge Flow receives exchanged token → uses `sub` field as author identifier

## 🔧 Components Modified

### Backend (Agentic)

#### 1. RuntimeContext Enhanced
**File**: `agentic_backend/app/core/agents/runtime_context.py`
- Added `user_token: str | None` field
- Added `get_user_token()` helper function

#### 2. TokenExchangeProvider Created
**File**: `fred-core/fred_core/security/outbound.py`
- Implements RFC 8693 Token Exchange
- Caches exchanged tokens for performance
- Handles errors gracefully with fallback to service tokens

#### 3. MCP Utils Adapted
**File**: `agentic_backend/app/common/mcp_utils.py`
- `_auth_headers()` attempts token exchange first if user token available
- Falls back to standard service account tokens
- Works with all MCP transports (HTTP and stdio)

#### 4. ApplicationContext Integrated
**File**: `agentic_backend/app/application_context.py`
- Creates `TokenExchangeProvider` instance
- Attaches to `OutboundAuth` for use in MCP calls

#### 5. WebSocket Handler Enhanced
**File**: `agentic_backend/app/core/chatbot/chatbot_controller.py`
- Handles authentication messages from frontend
- Extracts user token and enhances RuntimeContext
- Passes enhanced context to agents

#### 6. Agent Integration (Already Working)
- `AgentManager.get_agent_instance()` injects RuntimeContext into agents
- `AgentFlow.set_runtime_context()` stores the context
- `MCPRuntime` uses `context_provider` to access user token for exchange

### Frontend

#### WebSocket Client Enhanced  
**File**: `frontend/src/components/chatbot/ChatBot.tsx`
- Sends authentication message with user token on WebSocket connection
- Uses `KeyCloakService.GetToken()` to get current user token

## 📚 Documentation Updated

#### KEYCLOAK.md Enhanced
**File**: `docs/KEYCLOAK.md`
- Added Token Exchange configuration section
- Step-by-step Keycloak setup instructions
- Manual testing commands
- Architecture explanation

## 🚀 How to Test

### 1. Configure Keycloak
Follow instructions in `docs/KEYCLOAK.md#token-exchange-configuration-optional`

### 2. Run the System
```bash
# Terminal 1: Start Knowledge Flow
cd knowledge_flow_backend && make run

# Terminal 2: Start Agentic 
cd agentic_backend && make run

# Terminal 3: Start Frontend
cd frontend && make run
```

### 3. Test Token Exchange
1. Login as `alice` in the frontend
2. Create a resource via MCP (e.g., using ContentGeneratorExpert)
3. Check the `author` field in the Knowledge Flow database
4. Should show alice's unique identifier (`sub` field from JWT) instead of "service-account-agentic's"

### 4. Debug Logs
Enable debug logging in `agentic_backend/config/configuration.yaml`:
```yaml
app:
  log_level: debug
```

Look for these log messages:
- `"Received user token via WebSocket for OAuth2 Token Exchange"`
- `"Enhanced runtime context with user token for OAuth2 Token Exchange"`
- `"Using token exchange for user identity preservation"`
- `"Token exchange failed, falling back to service token"`

## 🛡️ Security Features

- ✅ User tokens never stored persistently, only cached during request lifecycle
- ✅ Token exchange requires proper Keycloak permissions
- ✅ Automatic fallback to service tokens if exchange fails
- ✅ All token operations logged for audit
- ✅ Tokens cached per user to minimize OAuth2 roundtrips

## 🔄 Fallback Behavior

If token exchange fails:
1. Log warning with error details
2. Automatically fallback to standard service account token
3. System continues to work (resilient design)
4. Author field will show "service-account-agentic" (original behavior)

## 📋 Requirements Met

- ✅ **User Identity Preservation**: Resources created show correct user as author
- ✅ **Security**: Cryptographically secure using OAuth2 standard
- ✅ **Performance**: Token caching minimizes overhead  
- ✅ **Resilience**: Graceful fallback if token exchange unavailable
- ✅ **Auditability**: Full logging of token operations
- ✅ **Standards Compliance**: Implements RFC 8693

## 🎉 Result

When alice creates a resource via MCP calls, the `author` field will now correctly show alice's unique identifier (`sub` field from JWT) instead of "service-account-agentic"!

## 🔍 Technical Details

### User Identity Preservation
The system now correctly preserves user identity through the following mechanism:

1. **Frontend**: User's JWT token contains `sub` field (unique identifier)
2. **Token Exchange**: RFC 8693 preserves the original `sub` field in the exchanged token  
3. **Knowledge Flow**: `get_current_user()` extracts `sub` from JWT and maps it to `user.uid`
4. **Result**: Resources are authored by the user's unique identifier, not the service account

### Key Code Points
- **JWT Decoding**: `fred-core/fred_core/security/keycloak.py:156` - Uses `payload.get("sub")` for `user.uid`
- **Token Exchange**: `fred-core/fred_core/security/outbound.py` - Preserves subject identity
- **Resource Creation**: Uses `user.uid` (which is the `sub` field) as author identifier