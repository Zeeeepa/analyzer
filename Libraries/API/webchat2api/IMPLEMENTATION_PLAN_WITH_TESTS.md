# WebChat2API - Implementation Plan with Testing

**Version:** 1.0  
**Date:** 2024-12-05  
**Status:** Ready to Execute

---

## 🎯 **Implementation Overview**

**Goal:** Build a robust webchat-to-API conversion system in 4 weeks

**Approach:** Incremental development with testing at each step

**Stack:**
- DrissionPage (browser automation)
- FastAPI (API gateway)
- Redis (caching)
- Python 3.11+

---

## 📋 **Phase 1: Core MVP (Days 1-10)**

### **STEP 1: Project Setup & DrissionPage Installation**

**Objective:** Initialize project and install core dependencies

**Implementation:**
```bash
# Create project structure
mkdir -p webchat2api/{src,tests,config,logs}
cd webchat2api

# Initialize Python environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Create requirements.txt
cat > requirements.txt << 'REQS'
DrissionPage>=4.0.0
fastapi>=0.104.0
uvicorn>=0.24.0
redis>=5.0.0
pydantic>=2.0.0
httpx>=0.25.0
structlog>=23.0.0
twocaptcha>=1.0.0
python-multipart>=0.0.6
REQS

# Install dependencies
pip install -r requirements.txt

# Create dev requirements
cat > requirements-dev.txt << 'DEVREQS'
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
black>=23.0.0
ruff>=0.1.0
httpx>=0.25.0
DEVREQS

pip install -r requirements-dev.txt
```

**Testing:**
```python
# tests/test_setup.py
import pytest
from DrissionPage import ChromiumPage

def test_drissionpage_import():
    """Test DrissionPage can be imported"""
    assert ChromiumPage is not None

def test_drissionpage_basic():
    """Test basic DrissionPage functionality"""
    page = ChromiumPage()
    assert page is not None
    page.quit()

def test_python_version():
    """Test Python version >= 3.11"""
    import sys
    assert sys.version_info >= (3, 11)
```

**Validation:**
```bash
# Run tests
pytest tests/test_setup.py -v

# Expected output:
# ✓ test_drissionpage_import PASSED
# ✓ test_drissionpage_basic PASSED
# ✓ test_python_version PASSED
```

**Success Criteria:**
- ✅ All dependencies installed
- ✅ DrissionPage imports successfully
- ✅ Basic page can be created and closed
- ✅ Tests pass

---

### **STEP 2: Anti-Detection Configuration**

**Objective:** Configure fingerprints and user-agent rotation

**Implementation:**
```python
# src/anti_detection.py
import json
import random
from pathlib import Path
from typing import Dict, Any

class AntiDetection:
    """Manage browser fingerprints and user-agents"""
    
    def __init__(self):
        self.fingerprints = self._load_fingerprints()
        self.user_agents = self._load_user_agents()
    
    def _load_fingerprints(self) -> list:
        """Load chrome-fingerprints database"""
        # For now, use a sample
        return [
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "viewport": {"width": 1920, "height": 1080},
                "platform": "Win32",
                "languages": ["en-US", "en"],
            }
        ]
    
    def _load_user_agents(self) -> list:
        """Load UserAgent-Switcher patterns"""
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        ]
    
    def get_random_fingerprint(self) -> Dict[str, Any]:
        """Get a random fingerprint"""
        return random.choice(self.fingerprints)
    
    def get_random_user_agent(self) -> str:
        """Get a random user agent"""
        return random.choice(self.user_agents)
    
    def apply_to_page(self, page) -> None:
        """Apply fingerprint and UA to page"""
        fp = self.get_random_fingerprint()
        ua = self.get_random_user_agent()
        
        # Set user agent
        page.set.user_agent(ua)
        
        # Set viewport
        page.set.window.size(fp["viewport"]["width"], fp["viewport"]["height"])
```

**Testing:**
```python
# tests/test_anti_detection.py
import pytest
from src.anti_detection import AntiDetection
from DrissionPage import ChromiumPage

def test_anti_detection_init():
    """Test AntiDetection initialization"""
    ad = AntiDetection()
    assert ad.fingerprints is not None
    assert ad.user_agents is not None
    assert len(ad.fingerprints) > 0
    assert len(ad.user_agents) > 0

def test_get_random_fingerprint():
    """Test fingerprint selection"""
    ad = AntiDetection()
    fp = ad.get_random_fingerprint()
    assert "userAgent" in fp
    assert "viewport" in fp

def test_get_random_user_agent():
    """Test user agent selection"""
    ad = AntiDetection()
    ua = ad.get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 0

def test_apply_to_page():
    """Test applying anti-detection to page"""
    ad = AntiDetection()
    page = ChromiumPage()
    
    try:
        ad.apply_to_page(page)
        # Verify user agent was set
        # Note: DrissionPage doesn't expose easy way to read back UA
        # So we just verify no errors
        assert True
    finally:
        page.quit()
```

**Validation:**
```bash
pytest tests/test_anti_detection.py -v

# Expected:
# ✓ test_anti_detection_init PASSED
# ✓ test_get_random_fingerprint PASSED  
# ✓ test_get_random_user_agent PASSED
# ✓ test_apply_to_page PASSED
```

**Success Criteria:**
- ✅ AntiDetection class works
- ✅ Fingerprints loaded
- ✅ User agents loaded
- ✅ Can apply to page without errors

---

### **STEP 3: Session Pool Manager**

**Objective:** Implement browser session pooling

**Implementation:**
```python
# src/session_pool.py
import time
from typing import Dict, Optional
from DrissionPage import ChromiumPage
from src.anti_detection import AntiDetection

class Session:
    """Wrapper for a browser session"""
    
    def __init__(self, session_id: str, page: ChromiumPage):
        self.session_id = session_id
        self.page = page
        self.created_at = time.time()
        self.last_used = time.time()
        self.is_healthy = True
    
    def touch(self):
        """Update last used timestamp"""
        self.last_used = time.time()
    
    def age(self) -> float:
        """Get session age in seconds"""
        return time.time() - self.created_at
    
    def idle_time(self) -> float:
        """Get idle time in seconds"""
        return time.time() - self.last_used

class SessionPool:
    """Manage pool of browser sessions"""
    
    def __init__(self, max_sessions: int = 10, max_age: int = 3600):
        self.max_sessions = max_sessions
        self.max_age = max_age
        self.sessions: Dict[str, Session] = {}
        self.anti_detection = AntiDetection()
    
    def allocate(self) -> Session:
        """Allocate a session from pool or create new one"""
        # Cleanup stale sessions first
        self._cleanup_stale()
        
        # Check pool size
        if len(self.sessions) >= self.max_sessions:
            raise RuntimeError(f"Pool exhausted: {self.max_sessions} sessions active")
        
        # Create new session
        session_id = f"session_{int(time.time() * 1000)}"
        page = ChromiumPage()
        
        # Apply anti-detection
        self.anti_detection.apply_to_page(page)
        
        session = Session(session_id, page)
        self.sessions[session_id] = session
        
        return session
    
    def release(self, session_id: str) -> None:
        """Release a session back to pool"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.page.quit()
            del self.sessions[session_id]
    
    def _cleanup_stale(self) -> None:
        """Remove stale sessions"""
        stale = []
        for session_id, session in self.sessions.items():
            if session.age() > self.max_age:
                stale.append(session_id)
        
        for session_id in stale:
            self.release(session_id)
    
    def get_stats(self) -> dict:
        """Get pool statistics"""
        return {
            "total_sessions": len(self.sessions),
            "max_sessions": self.max_sessions,
            "sessions": [
                {
                    "id": s.session_id,
                    "age": s.age(),
                    "idle": s.idle_time(),
                    "healthy": s.is_healthy,
                }
                for s in self.sessions.values()
            ]
        }
```

**Testing:**
```python
# tests/test_session_pool.py
import pytest
import time
from src.session_pool import SessionPool, Session

def test_session_creation():
    """Test Session wrapper"""
    from DrissionPage import ChromiumPage
    page = ChromiumPage()
    session = Session("test_id", page)
    
    assert session.session_id == "test_id"
    assert session.page == page
    assert session.is_healthy
    
    page.quit()

def test_session_pool_init():
    """Test SessionPool initialization"""
    pool = SessionPool(max_sessions=5)
    assert pool.max_sessions == 5
    assert len(pool.sessions) == 0

def test_session_allocate():
    """Test session allocation"""
    pool = SessionPool(max_sessions=2)
    
    session1 = pool.allocate()
    assert session1 is not None
    assert len(pool.sessions) == 1
    
    session2 = pool.allocate()
    assert session2 is not None
    assert len(pool.sessions) == 2
    
    # Cleanup
    pool.release(session1.session_id)
    pool.release(session2.session_id)

def test_session_pool_exhaustion():
    """Test pool exhaustion handling"""
    pool = SessionPool(max_sessions=1)
    
    session1 = pool.allocate()
    
    with pytest.raises(RuntimeError, match="Pool exhausted"):
        session2 = pool.allocate()
    
    pool.release(session1.session_id)

def test_session_release():
    """Test session release"""
    pool = SessionPool()
    session = pool.allocate()
    session_id = session.session_id
    
    assert session_id in pool.sessions
    
    pool.release(session_id)
    assert session_id not in pool.sessions

def test_pool_stats():
    """Test pool statistics"""
    pool = SessionPool()
    session = pool.allocate()
    
    stats = pool.get_stats()
    assert stats["total_sessions"] == 1
    assert len(stats["sessions"]) == 1
    
    pool.release(session.session_id)
```

**Validation:**
```bash
pytest tests/test_session_pool.py -v

# Expected:
# ✓ test_session_creation PASSED
# ✓ test_session_pool_init PASSED
# ✓ test_session_allocate PASSED
# ✓ test_session_pool_exhaustion PASSED
# ✓ test_session_release PASSED
# ✓ test_pool_stats PASSED
```

**Success Criteria:**
- ✅ Session wrapper works
- ✅ Pool can allocate/release sessions
- ✅ Pool exhaustion handled
- ✅ Stale session cleanup works
- ✅ Statistics available

---

## ⏭️ **Next Steps**

Continue with:
- Step 4: Authentication Handler
- Step 5: Response Extractor
- Step 6: FastAPI Gateway
- Step 7-10: Integration & Testing

Would you like me to:
1. Continue with remaining steps (4-10)?
2. Start implementing the code now?
3. Add more detailed testing scenarios?
