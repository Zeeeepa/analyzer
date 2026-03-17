"""
Site Memory - Cache Synthesized Selectors and Interaction Patterns

Stores per-site knowledge:
1. Successful selectors for common elements
2. Obstruction patterns and dismissal methods
3. Page structure fingerprints
4. Interaction timing preferences

Benefits:
- Skip vision calls for known elements
- Faster repeat visits to same site
- Learn from successful interactions
"""

import asyncio
import os
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

# Optional aiosqlite for async database operations
try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    aiosqlite = None
    HAS_AIOSQLITE = False


@dataclass
class CachedSelector:
    """Cached selector with success metrics."""
    selector: str
    element_description: str  # "login button", "search input"
    success_count: int
    failure_count: int
    last_used: datetime
    last_success: datetime
    confidence: float  # Calculated from success/failure ratio
    fallbacks: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'selector': self.selector,
            'element_description': self.element_description,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'last_used': self.last_used.isoformat(),
            'last_success': self.last_success.isoformat(),
            'confidence': self.confidence,
            'fallbacks': self.fallbacks
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CachedSelector':
        """Create from dictionary."""
        return cls(
            selector=data['selector'],
            element_description=data['element_description'],
            success_count=data['success_count'],
            failure_count=data['failure_count'],
            last_used=datetime.fromisoformat(data['last_used']),
            last_success=datetime.fromisoformat(data['last_success']),
            confidence=data['confidence'],
            fallbacks=data['fallbacks']
        )


@dataclass
class ObstructionPattern:
    """Known obstruction pattern for a site."""
    domain: str
    obstruction_type: str  # "cookie_banner", "modal", "popup", "overlay"
    detection_selector: str
    dismiss_selector: str
    dismiss_method: str  # "click", "esc", "click_outside"
    success_rate: float
    last_seen: datetime
    total_dismissals: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'domain': self.domain,
            'obstruction_type': self.obstruction_type,
            'detection_selector': self.detection_selector,
            'dismiss_selector': self.dismiss_selector,
            'dismiss_method': self.dismiss_method,
            'success_rate': self.success_rate,
            'last_seen': self.last_seen.isoformat(),
            'total_dismissals': self.total_dismissals
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ObstructionPattern':
        """Create from dictionary."""
        return cls(
            domain=data['domain'],
            obstruction_type=data['obstruction_type'],
            detection_selector=data['detection_selector'],
            dismiss_selector=data['dismiss_selector'],
            dismiss_method=data['dismiss_method'],
            success_rate=data['success_rate'],
            last_seen=datetime.fromisoformat(data['last_seen']),
            total_dismissals=data['total_dismissals']
        )


@dataclass
class PageFingerprint:
    """Page structure fingerprint."""
    domain: str
    page_type: str  # "login", "search", "product", "checkout"
    url_pattern: str  # Regex or glob pattern
    key_elements: Dict[str, str]  # {"login_form": "form#login", ...}
    detected_framework: str  # "react", "vue", "angular", "vanilla"
    dynamic_class_patterns: List[str]  # Patterns to avoid (e.g., "css-.*", "makeStyles-.*")
    last_updated: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'domain': self.domain,
            'page_type': self.page_type,
            'url_pattern': self.url_pattern,
            'key_elements': self.key_elements,
            'detected_framework': self.detected_framework,
            'dynamic_class_patterns': self.dynamic_class_patterns,
            'last_updated': self.last_updated.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PageFingerprint':
        """Create from dictionary."""
        return cls(
            domain=data['domain'],
            page_type=data['page_type'],
            url_pattern=data['url_pattern'],
            key_elements=data['key_elements'],
            detected_framework=data['detected_framework'],
            dynamic_class_patterns=data['dynamic_class_patterns'],
            last_updated=datetime.fromisoformat(data['last_updated'])
        )


@dataclass
class InteractionTiming:
    """Learned interaction timing for a domain."""
    domain: str
    avg_page_load_time: float
    recommended_wait_after_click: float
    recommended_typing_speed: float  # chars per second
    needs_extra_wait: bool  # Slow site
    sample_count: int
    last_updated: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'domain': self.domain,
            'avg_page_load_time': self.avg_page_load_time,
            'recommended_wait_after_click': self.recommended_wait_after_click,
            'recommended_typing_speed': self.recommended_typing_speed,
            'needs_extra_wait': self.needs_extra_wait,
            'sample_count': self.sample_count,
            'last_updated': self.last_updated.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InteractionTiming':
        """Create from dictionary."""
        return cls(
            domain=data['domain'],
            avg_page_load_time=data['avg_page_load_time'],
            recommended_wait_after_click=data['recommended_wait_after_click'],
            recommended_typing_speed=data['recommended_typing_speed'],
            needs_extra_wait=data['needs_extra_wait'],
            sample_count=data['sample_count'],
            last_updated=datetime.fromisoformat(data['last_updated'])
        )


class SelectorCache:
    """Cache for selectors with success tracking."""

    def __init__(self, db_conn):
        """Initialize with database connection (aiosqlite.Connection or None)."""
        self.db = db_conn

    async def get_selector(self, domain: str, element_desc: str) -> Optional[CachedSelector]:
        """Get cached selector for element on domain."""
        async with self.db.execute(
            """
            SELECT selector, element_description, success_count, failure_count,
                   last_used, last_success, confidence, fallbacks
            FROM selectors
            WHERE domain = ? AND element_description = ?
            ORDER BY confidence DESC, last_success DESC
            LIMIT 1
            """,
            (domain, element_desc)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return CachedSelector(
                    selector=row[0],
                    element_description=row[1],
                    success_count=row[2],
                    failure_count=row[3],
                    last_used=datetime.fromisoformat(row[4]),
                    last_success=datetime.fromisoformat(row[5]),
                    confidence=row[6],
                    fallbacks=json.loads(row[7]) if row[7] else []
                )
        return None

    async def store_selector(
        self,
        domain: str,
        element_desc: str,
        selector: str,
        success: bool,
        fallbacks: Optional[List[str]] = None
    ):
        """Store or update selector with success/failure."""
        fallbacks = fallbacks or []

        # Check if selector exists
        async with self.db.execute(
            "SELECT success_count, failure_count FROM selectors WHERE domain = ? AND element_description = ? AND selector = ?",
            (domain, element_desc, selector)
        ) as cursor:
            row = await cursor.fetchone()

        now = datetime.now()

        if row:
            # Update existing
            success_count = row[0] + (1 if success else 0)
            failure_count = row[1] + (0 if success else 1)
            confidence = success_count / (success_count + failure_count) if (success_count + failure_count) > 0 else 0.0

            await self.db.execute(
                """
                UPDATE selectors
                SET success_count = ?, failure_count = ?, last_used = ?, last_success = ?, confidence = ?, fallbacks = ?
                WHERE domain = ? AND element_description = ? AND selector = ?
                """,
                (
                    success_count, failure_count, now.isoformat(),
                    now.isoformat() if success else row[1],
                    confidence,
                    json.dumps(fallbacks),
                    domain, element_desc, selector
                )
            )
        else:
            # Insert new
            success_count = 1 if success else 0
            failure_count = 0 if success else 1
            confidence = 1.0 if success else 0.0

            await self.db.execute(
                """
                INSERT INTO selectors (domain, element_description, selector, success_count, failure_count, last_used, last_success, confidence, fallbacks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (domain, element_desc, selector, success_count, failure_count, now.isoformat(), now.isoformat(), confidence, json.dumps(fallbacks))
            )

        await self.db.commit()

    async def get_best_selector(self, domain: str, element_desc: str) -> Optional[str]:
        """Get highest confidence selector for element."""
        selector = await self.get_selector(domain, element_desc)
        return selector.selector if selector else None

    async def get_all_selectors(self, domain: str, element_desc: str, min_confidence: float = 0.5) -> List[CachedSelector]:
        """Get all selectors for element above confidence threshold."""
        async with self.db.execute(
            """
            SELECT selector, element_description, success_count, failure_count,
                   last_used, last_success, confidence, fallbacks
            FROM selectors
            WHERE domain = ? AND element_description = ? AND confidence >= ?
            ORDER BY confidence DESC, last_success DESC
            """,
            (domain, element_desc, min_confidence)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                CachedSelector(
                    selector=row[0],
                    element_description=row[1],
                    success_count=row[2],
                    failure_count=row[3],
                    last_used=datetime.fromisoformat(row[4]),
                    last_success=datetime.fromisoformat(row[5]),
                    confidence=row[6],
                    fallbacks=json.loads(row[7]) if row[7] else []
                )
                for row in rows
            ]


class ObstructionMemory:
    """Memory for obstruction patterns."""

    def __init__(self, db_conn):
        """Initialize with database connection."""
        self.db = db_conn

    async def get_known_obstructions(self, domain: str) -> List[ObstructionPattern]:
        """Get known obstruction patterns for domain."""
        async with self.db.execute(
            """
            SELECT domain, obstruction_type, detection_selector, dismiss_selector,
                   dismiss_method, success_rate, last_seen, total_dismissals
            FROM obstructions
            WHERE domain = ? AND success_rate >= 0.5
            ORDER BY success_rate DESC, last_seen DESC
            """,
            (domain,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                ObstructionPattern(
                    domain=row[0],
                    obstruction_type=row[1],
                    detection_selector=row[2],
                    dismiss_selector=row[3],
                    dismiss_method=row[4],
                    success_rate=row[5],
                    last_seen=datetime.fromisoformat(row[6]),
                    total_dismissals=row[7]
                )
                for row in rows
            ]

    async def store_obstruction(self, pattern: ObstructionPattern):
        """Store learned obstruction pattern."""
        # Check if exists
        async with self.db.execute(
            """
            SELECT total_dismissals, success_rate
            FROM obstructions
            WHERE domain = ? AND obstruction_type = ? AND detection_selector = ?
            """,
            (pattern.domain, pattern.obstruction_type, pattern.detection_selector)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            # Update existing - exponential moving average for success rate
            old_dismissals = row[0]
            old_success_rate = row[1]
            new_dismissals = old_dismissals + 1
            alpha = 0.3  # Weight for new observation
            new_success_rate = alpha * pattern.success_rate + (1 - alpha) * old_success_rate

            await self.db.execute(
                """
                UPDATE obstructions
                SET dismiss_selector = ?, dismiss_method = ?, success_rate = ?, last_seen = ?, total_dismissals = ?
                WHERE domain = ? AND obstruction_type = ? AND detection_selector = ?
                """,
                (
                    pattern.dismiss_selector, pattern.dismiss_method, new_success_rate,
                    pattern.last_seen.isoformat(), new_dismissals,
                    pattern.domain, pattern.obstruction_type, pattern.detection_selector
                )
            )
        else:
            # Insert new
            await self.db.execute(
                """
                INSERT INTO obstructions (domain, obstruction_type, detection_selector, dismiss_selector, dismiss_method, success_rate, last_seen, total_dismissals)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pattern.domain, pattern.obstruction_type, pattern.detection_selector,
                    pattern.dismiss_selector, pattern.dismiss_method, pattern.success_rate,
                    pattern.last_seen.isoformat(), pattern.total_dismissals
                )
            )

        await self.db.commit()


class PageStructureCache:
    """Cache for page structure fingerprints."""

    def __init__(self, db_conn):
        """Initialize with database connection."""
        self.db = db_conn

    async def get_fingerprint(self, domain: str, url_pattern: str) -> Optional[PageFingerprint]:
        """Get cached page structure."""
        async with self.db.execute(
            """
            SELECT domain, page_type, url_pattern, key_elements, detected_framework, dynamic_class_patterns, last_updated
            FROM page_fingerprints
            WHERE domain = ? AND url_pattern = ?
            """,
            (domain, url_pattern)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return PageFingerprint(
                    domain=row[0],
                    page_type=row[1],
                    url_pattern=row[2],
                    key_elements=json.loads(row[3]) if row[3] else {},
                    detected_framework=row[4],
                    dynamic_class_patterns=json.loads(row[5]) if row[5] else [],
                    last_updated=datetime.fromisoformat(row[6])
                )
        return None

    async def store_fingerprint(self, fingerprint: PageFingerprint):
        """Store page structure."""
        # Upsert
        await self.db.execute(
            """
            INSERT INTO page_fingerprints (domain, page_type, url_pattern, key_elements, detected_framework, dynamic_class_patterns, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain, url_pattern) DO UPDATE SET
                page_type = excluded.page_type,
                key_elements = excluded.key_elements,
                detected_framework = excluded.detected_framework,
                dynamic_class_patterns = excluded.dynamic_class_patterns,
                last_updated = excluded.last_updated
            """,
            (
                fingerprint.domain,
                fingerprint.page_type,
                fingerprint.url_pattern,
                json.dumps(fingerprint.key_elements),
                fingerprint.detected_framework,
                json.dumps(fingerprint.dynamic_class_patterns),
                fingerprint.last_updated.isoformat()
            )
        )
        await self.db.commit()

    async def get_fingerprints_by_domain(self, domain: str) -> List[PageFingerprint]:
        """Get all fingerprints for a domain."""
        async with self.db.execute(
            "SELECT domain, page_type, url_pattern, key_elements, detected_framework, dynamic_class_patterns, last_updated FROM page_fingerprints WHERE domain = ?",
            (domain,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                PageFingerprint(
                    domain=row[0],
                    page_type=row[1],
                    url_pattern=row[2],
                    key_elements=json.loads(row[3]) if row[3] else {},
                    detected_framework=row[4],
                    dynamic_class_patterns=json.loads(row[5]) if row[5] else [],
                    last_updated=datetime.fromisoformat(row[6])
                )
                for row in rows
            ]


class TimingMemory:
    """Memory for interaction timing."""

    def __init__(self, db_conn):
        """Initialize with database connection."""
        self.db = db_conn

    async def get_timing(self, domain: str) -> Optional[InteractionTiming]:
        """Get recommended timing for domain."""
        async with self.db.execute(
            """
            SELECT domain, avg_page_load_time, recommended_wait_after_click, recommended_typing_speed, needs_extra_wait, sample_count, last_updated
            FROM interaction_timings
            WHERE domain = ?
            """,
            (domain,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return InteractionTiming(
                    domain=row[0],
                    avg_page_load_time=row[1],
                    recommended_wait_after_click=row[2],
                    recommended_typing_speed=row[3],
                    needs_extra_wait=bool(row[4]),
                    sample_count=row[5],
                    last_updated=datetime.fromisoformat(row[6])
                )
        return None

    async def update_timing(self, domain: str, action: str, duration: float):
        """Update timing based on actual performance."""
        timing = await self.get_timing(domain)

        if timing:
            # Update with exponential moving average
            alpha = 0.2  # Weight for new observation
            sample_count = timing.sample_count + 1

            if action == "page_load":
                avg_load = alpha * duration + (1 - alpha) * timing.avg_page_load_time
                needs_extra = avg_load > 3.0
                await self.db.execute(
                    """
                    UPDATE interaction_timings
                    SET avg_page_load_time = ?, needs_extra_wait = ?, sample_count = ?, last_updated = ?
                    WHERE domain = ?
                    """,
                    (avg_load, needs_extra, sample_count, datetime.now().isoformat(), domain)
                )
            elif action == "click":
                wait_after = alpha * duration + (1 - alpha) * timing.recommended_wait_after_click
                await self.db.execute(
                    """
                    UPDATE interaction_timings
                    SET recommended_wait_after_click = ?, sample_count = ?, last_updated = ?
                    WHERE domain = ?
                    """,
                    (wait_after, sample_count, datetime.now().isoformat(), domain)
                )
            elif action == "typing":
                typing_speed = alpha * duration + (1 - alpha) * timing.recommended_typing_speed
                await self.db.execute(
                    """
                    UPDATE interaction_timings
                    SET recommended_typing_speed = ?, sample_count = ?, last_updated = ?
                    WHERE domain = ?
                    """,
                    (typing_speed, sample_count, datetime.now().isoformat(), domain)
                )
        else:
            # Insert new
            if action == "page_load":
                await self.db.execute(
                    """
                    INSERT INTO interaction_timings (domain, avg_page_load_time, recommended_wait_after_click, recommended_typing_speed, needs_extra_wait, sample_count, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (domain, duration, 0.5, 10.0, duration > 3.0, 1, datetime.now().isoformat())
                )
            elif action == "click":
                await self.db.execute(
                    """
                    INSERT INTO interaction_timings (domain, avg_page_load_time, recommended_wait_after_click, recommended_typing_speed, needs_extra_wait, sample_count, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (domain, 1.5, duration, 10.0, False, 1, datetime.now().isoformat())
                )
            elif action == "typing":
                await self.db.execute(
                    """
                    INSERT INTO interaction_timings (domain, avg_page_load_time, recommended_wait_after_click, recommended_typing_speed, needs_extra_wait, sample_count, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (domain, 1.5, 0.5, duration, False, 1, datetime.now().isoformat())
                )

        await self.db.commit()


class SiteMemory:
    """Unified interface for site memory."""

    # Database schema version
    SCHEMA_VERSION = 1

    # Database schema
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    );

    CREATE TABLE IF NOT EXISTS selectors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        element_description TEXT NOT NULL,
        selector TEXT NOT NULL,
        success_count INTEGER DEFAULT 0,
        failure_count INTEGER DEFAULT 0,
        last_used TEXT NOT NULL,
        last_success TEXT NOT NULL,
        confidence REAL DEFAULT 0.0,
        fallbacks TEXT,
        UNIQUE(domain, element_description, selector)
    );

    CREATE INDEX IF NOT EXISTS idx_selectors_domain_desc ON selectors(domain, element_description);
    CREATE INDEX IF NOT EXISTS idx_selectors_confidence ON selectors(confidence DESC);

    CREATE TABLE IF NOT EXISTS obstructions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        obstruction_type TEXT NOT NULL,
        detection_selector TEXT NOT NULL,
        dismiss_selector TEXT NOT NULL,
        dismiss_method TEXT NOT NULL,
        success_rate REAL DEFAULT 0.0,
        last_seen TEXT NOT NULL,
        total_dismissals INTEGER DEFAULT 0,
        UNIQUE(domain, obstruction_type, detection_selector)
    );

    CREATE INDEX IF NOT EXISTS idx_obstructions_domain ON obstructions(domain);

    CREATE TABLE IF NOT EXISTS page_fingerprints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        page_type TEXT NOT NULL,
        url_pattern TEXT NOT NULL,
        key_elements TEXT,
        detected_framework TEXT,
        dynamic_class_patterns TEXT,
        last_updated TEXT NOT NULL,
        UNIQUE(domain, url_pattern)
    );

    CREATE INDEX IF NOT EXISTS idx_fingerprints_domain ON page_fingerprints(domain);

    CREATE TABLE IF NOT EXISTS interaction_timings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL UNIQUE,
        avg_page_load_time REAL DEFAULT 1.5,
        recommended_wait_after_click REAL DEFAULT 0.5,
        recommended_typing_speed REAL DEFAULT 10.0,
        needs_extra_wait INTEGER DEFAULT 0,
        sample_count INTEGER DEFAULT 0,
        last_updated TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_timings_domain ON interaction_timings(domain);
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to ~/.eversale/site_memory.db
            home = Path.home()
            eversale_dir = home / ".eversale"
            eversale_dir.mkdir(exist_ok=True)
            db_path = str(eversale_dir / "site_memory.db")

        self.db_path = db_path
        self.db = None  # aiosqlite.Connection when available
        self.selector_cache: Optional[SelectorCache] = None
        self.obstruction_memory: Optional[ObstructionMemory] = None
        self.page_structure: Optional[PageStructureCache] = None
        self.timing_memory: Optional[TimingMemory] = None
        self._initialized = False

    async def initialize(self):
        """Initialize database and create tables."""
        if self._initialized:
            return

        if not HAS_AIOSQLITE:
            # Fallback: use in-memory cache without persistence
            from loguru import logger
            logger.warning("aiosqlite not available - site memory will not persist")
            self._initialized = True
            return

        self.db = await aiosqlite.connect(self.db_path)

        # Create schema
        await self.db.executescript(self.SCHEMA)

        # Check schema version
        async with self.db.execute("SELECT version FROM schema_version") as cursor:
            row = await cursor.fetchone()
            if not row:
                await self.db.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
                await self.db.commit()

        # Initialize subsystems
        self.selector_cache = SelectorCache(self.db)
        self.obstruction_memory = ObstructionMemory(self.db)
        self.page_structure = PageStructureCache(self.db)
        self.timing_memory = TimingMemory(self.db)

        self._initialized = True

    async def close(self):
        """Close database connection."""
        if self.db:
            await self.db.close()
            self.db = None
            self._initialized = False

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc or url

    async def get_selector(self, url: str, element_desc: str) -> Optional[str]:
        """Primary interface for getting cached selector."""
        if not self._initialized:
            await self.initialize()

        # No database - can't retrieve cached selectors
        if not self.selector_cache:
            return None

        domain = self._extract_domain(url)
        return await self.selector_cache.get_best_selector(domain, element_desc)

    async def learn_from_interaction(
        self,
        url: str,
        element_desc: str,
        selector_used: str,
        success: bool,
        method: str,  # "cached", "css", "vision", etc.
        timing: float,
        fallbacks: Optional[List[str]] = None
    ):
        """Learn from successful/failed interaction."""
        if not self._initialized:
            await self.initialize()

        # No database - can't store learnings
        if not self.selector_cache:
            return

        domain = self._extract_domain(url)

        # Store selector result
        await self.selector_cache.store_selector(
            domain=domain,
            element_desc=element_desc,
            selector=selector_used,
            success=success,
            fallbacks=fallbacks
        )

        # Update timing if interaction succeeded
        if success and self.timing_memory:
            if method in ["click", "vision_click"]:
                await self.timing_memory.update_timing(domain, "click", timing)
            elif method in ["fill", "type", "vision_type"]:
                await self.timing_memory.update_timing(domain, "typing", timing)

    async def store_obstruction_pattern(
        self,
        url: str,
        obstruction_type: str,
        detection_selector: str,
        dismiss_selector: str,
        dismiss_method: str,
        success: bool
    ):
        """Store learned obstruction pattern."""
        if not self._initialized:
            await self.initialize()

        if not self.obstruction_memory:
            return

        domain = self._extract_domain(url)
        pattern = ObstructionPattern(
            domain=domain,
            obstruction_type=obstruction_type,
            detection_selector=detection_selector,
            dismiss_selector=dismiss_selector,
            dismiss_method=dismiss_method,
            success_rate=1.0 if success else 0.0,
            last_seen=datetime.now(),
            total_dismissals=1
        )
        await self.obstruction_memory.store_obstruction(pattern)

    async def get_obstructions(self, url: str) -> List[ObstructionPattern]:
        """Get known obstructions for URL."""
        if not self._initialized:
            await self.initialize()

        if not self.obstruction_memory:
            return []

        domain = self._extract_domain(url)
        return await self.obstruction_memory.get_known_obstructions(domain)

    async def store_page_structure(
        self,
        url: str,
        page_type: str,
        key_elements: Dict[str, str],
        detected_framework: str,
        dynamic_class_patterns: Optional[List[str]] = None
    ):
        """Store page structure fingerprint."""
        if not self._initialized:
            await self.initialize()

        if not self.page_structure:
            return

        domain = self._extract_domain(url)
        parsed = urlparse(url)
        url_pattern = parsed.path or "/"

        fingerprint = PageFingerprint(
            domain=domain,
            page_type=page_type,
            url_pattern=url_pattern,
            key_elements=key_elements,
            detected_framework=detected_framework,
            dynamic_class_patterns=dynamic_class_patterns or [],
            last_updated=datetime.now()
        )
        await self.page_structure.store_fingerprint(fingerprint)

    async def get_page_structure(self, url: str) -> Optional[PageFingerprint]:
        """Get page structure for URL."""
        if not self._initialized:
            await self.initialize()

        if not self.page_structure:
            return None

        domain = self._extract_domain(url)
        parsed = urlparse(url)
        url_pattern = parsed.path or "/"

        return await self.page_structure.get_fingerprint(domain, url_pattern)

    async def get_timing(self, url: str) -> Optional[InteractionTiming]:
        """Get interaction timing for URL."""
        if not self._initialized:
            await self.initialize()

        if not self.timing_memory:
            return None

        domain = self._extract_domain(url)
        return await self.timing_memory.get_timing(domain)

    async def cleanup_old_entries(self, days: int = 90):
        """Remove entries older than N days."""
        if not self._initialized:
            await self.initialize()

        if not self.db:
            return

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # Clean selectors with low confidence and old
        await self.db.execute(
            "DELETE FROM selectors WHERE confidence < 0.3 AND last_used < ?",
            (cutoff,)
        )

        # Clean obstructions not seen recently
        await self.db.execute(
            "DELETE FROM obstructions WHERE last_seen < ?",
            (cutoff,)
        )

        # Clean old fingerprints
        await self.db.execute(
            "DELETE FROM page_fingerprints WHERE last_updated < ?",
            (cutoff,)
        )

        # Clean timings not updated recently
        await self.db.execute(
            "DELETE FROM interaction_timings WHERE last_updated < ?",
            (cutoff,)
        )

        await self.db.commit()

    async def export_to_json(self, output_path: str):
        """Export all memory to JSON file."""
        if not self._initialized:
            await self.initialize()

        if not self.db:
            # No database - nothing to export
            return

        data = {
            "version": self.SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(),
            "selectors": [],
            "obstructions": [],
            "fingerprints": [],
            "timings": []
        }

        # Export selectors
        async with self.db.execute("SELECT * FROM selectors") as cursor:
            async for row in cursor:
                data["selectors"].append({
                    "domain": row[1],
                    "element_description": row[2],
                    "selector": row[3],
                    "success_count": row[4],
                    "failure_count": row[5],
                    "last_used": row[6],
                    "last_success": row[7],
                    "confidence": row[8],
                    "fallbacks": json.loads(row[9]) if row[9] else []
                })

        # Export obstructions
        async with self.db.execute("SELECT * FROM obstructions") as cursor:
            async for row in cursor:
                data["obstructions"].append({
                    "domain": row[1],
                    "obstruction_type": row[2],
                    "detection_selector": row[3],
                    "dismiss_selector": row[4],
                    "dismiss_method": row[5],
                    "success_rate": row[6],
                    "last_seen": row[7],
                    "total_dismissals": row[8]
                })

        # Export fingerprints
        async with self.db.execute("SELECT * FROM page_fingerprints") as cursor:
            async for row in cursor:
                data["fingerprints"].append({
                    "domain": row[1],
                    "page_type": row[2],
                    "url_pattern": row[3],
                    "key_elements": json.loads(row[4]) if row[4] else {},
                    "detected_framework": row[5],
                    "dynamic_class_patterns": json.loads(row[6]) if row[6] else [],
                    "last_updated": row[7]
                })

        # Export timings
        async with self.db.execute("SELECT * FROM interaction_timings") as cursor:
            async for row in cursor:
                data["timings"].append({
                    "domain": row[1],
                    "avg_page_load_time": row[2],
                    "recommended_wait_after_click": row[3],
                    "recommended_typing_speed": row[4],
                    "needs_extra_wait": bool(row[5]),
                    "sample_count": row[6],
                    "last_updated": row[7]
                })

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

    async def import_from_json(self, input_path: str):
        """Import memory from JSON file."""
        if not self._initialized:
            await self.initialize()

        if not self.db:
            # No database - can't import
            return

        with open(input_path, 'r') as f:
            data = json.load(f)

        # Import selectors
        if self.selector_cache:
            for item in data.get("selectors", []):
                await self.selector_cache.store_selector(
                    domain=item["domain"],
                    element_desc=item["element_description"],
                    selector=item["selector"],
                    success=item["success_count"] > 0,
                    fallbacks=item.get("fallbacks", [])
                )

        # Import obstructions
        if self.obstruction_memory:
            for item in data.get("obstructions", []):
                pattern = ObstructionPattern(
                    domain=item["domain"],
                    obstruction_type=item["obstruction_type"],
                    detection_selector=item["detection_selector"],
                    dismiss_selector=item["dismiss_selector"],
                    dismiss_method=item["dismiss_method"],
                    success_rate=item["success_rate"],
                    last_seen=datetime.fromisoformat(item["last_seen"]),
                    total_dismissals=item["total_dismissals"]
                )
                await self.obstruction_memory.store_obstruction(pattern)

        # Import fingerprints
        if self.page_structure:
            for item in data.get("fingerprints", []):
                fingerprint = PageFingerprint(
                    domain=item["domain"],
                    page_type=item["page_type"],
                    url_pattern=item["url_pattern"],
                    key_elements=item["key_elements"],
                    detected_framework=item["detected_framework"],
                    dynamic_class_patterns=item["dynamic_class_patterns"],
                    last_updated=datetime.fromisoformat(item["last_updated"])
                )
                await self.page_structure.store_fingerprint(fingerprint)

        # Import timings - handled by update_timing
        for item in data.get("timings", []):
            timing = InteractionTiming(
                domain=item["domain"],
                avg_page_load_time=item["avg_page_load_time"],
                recommended_wait_after_click=item["recommended_wait_after_click"],
                recommended_typing_speed=item["recommended_typing_speed"],
                needs_extra_wait=item["needs_extra_wait"],
                sample_count=item["sample_count"],
                last_updated=datetime.fromisoformat(item["last_updated"])
            )
            # Insert directly
            await self.db.execute(
                """
                INSERT OR REPLACE INTO interaction_timings (domain, avg_page_load_time, recommended_wait_after_click, recommended_typing_speed, needs_extra_wait, sample_count, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timing.domain,
                    timing.avg_page_load_time,
                    timing.recommended_wait_after_click,
                    timing.recommended_typing_speed,
                    timing.needs_extra_wait,
                    timing.sample_count,
                    timing.last_updated.isoformat()
                )
            )

        await self.db.commit()


# Global instance
_site_memory: Optional[SiteMemory] = None
_memory_lock = asyncio.Lock()


async def get_site_memory() -> SiteMemory:
    """Get global site memory instance."""
    global _site_memory
    async with _memory_lock:
        if _site_memory is None:
            _site_memory = SiteMemory()
            await _site_memory.initialize()
        return _site_memory


async def close_site_memory():
    """Close global site memory instance."""
    global _site_memory
    async with _memory_lock:
        if _site_memory is not None:
            await _site_memory.close()
            _site_memory = None
