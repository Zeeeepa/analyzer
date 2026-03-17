"""
Session Sharing System for Eversale Agent

This module provides functionality to share agent sessions with others.
Based on OpenCode's share/share.ts implementation, it includes:

- SessionSharer class for creating and managing shareable sessions
- Promise queue for sequential sync processing
- Pending map for tracking unsynchronized changes
- Data endpoints for session info, messages, and message parts
- Export format with diff support
- Secret-based authentication

Architecture:
- Sessions are exported to JSON with unique share secrets
- Changes are synced incrementally (not full session each time)
- Share URLs include session ID but secret is separate
- Server validates secrets before returning session data
"""

import json
import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from loguru import logger
import asyncio
from collections import defaultdict


# Shares directory
SHARES_DIR = Path("memory/shares")
SHARES_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ShareMetadata:
    """
    Metadata for a shared session.

    Attributes:
        session_id: The session being shared
        secret: Secret key for authentication
        share_key: Unique share identifier
        created_at: When the share was created
        last_synced_at: Last sync timestamp
        sync_count: Number of times synced
        message_ids: Set of synced message IDs
        part_ids: Set of synced part IDs
    """
    session_id: str
    secret: str
    share_key: str
    created_at: str
    last_synced_at: Optional[str] = None
    sync_count: int = 0
    message_ids: Set[str] = field(default_factory=set)
    part_ids: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'session_id': self.session_id,
            'secret': self.secret,
            'share_key': self.share_key,
            'created_at': self.created_at,
            'last_synced_at': self.last_synced_at,
            'sync_count': self.sync_count,
            'message_ids': list(self.message_ids),
            'part_ids': list(self.part_ids)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShareMetadata':
        """Create from dictionary."""
        return cls(
            session_id=data['session_id'],
            secret=data['secret'],
            share_key=data['share_key'],
            created_at=data['created_at'],
            last_synced_at=data.get('last_synced_at'),
            sync_count=data.get('sync_count', 0),
            message_ids=set(data.get('message_ids', [])),
            part_ids=set(data.get('part_ids', []))
        )


@dataclass
class SyncTask:
    """
    Represents a pending sync task.

    Attributes:
        session_id: Session to sync
        task_type: Type of sync (full, message, part)
        payload: Data to sync
        timestamp: When task was created
    """
    session_id: str
    task_type: str
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class SessionSharer:
    """
    Manages session sharing with URL generation and incremental sync.

    Features:
    - Create shareable URLs with secret authentication
    - Sequential sync processing via promise queue
    - Track unsynchronized changes in pending map
    - Export session data in diff format
    - Manage share lifecycle (create, sync, delete)

    Example:
        sharer = SessionSharer(base_url="https://eversale.io")

        # Create share
        share_url, secret = sharer.create_share(session_id="session_123")

        # Sync session data
        await sharer.sync_session(session_id="session_123", session_data=data)

        # Get share URL
        url = sharer.get_share_url(session_id="session_123")

        # Delete share
        sharer.delete_share(session_id="session_123")
    """

    def __init__(self, base_url: str = "https://eversale.io"):
        """
        Initialize SessionSharer.

        Args:
            base_url: Base URL for share links (default: https://eversale.io)
        """
        self.base_url = base_url.rstrip('/')
        self._shares: Dict[str, ShareMetadata] = {}
        self._pending_syncs: Dict[str, List[SyncTask]] = defaultdict(list)
        self._sync_queue: asyncio.Queue = asyncio.Queue()
        self._processing = False

        # Load existing shares
        self._load_shares()

        logger.info("SessionSharer initialized")

    def _load_shares(self):
        """Load existing shares from disk."""
        metadata_file = SHARES_DIR / "shares_metadata.json"
        if metadata_file.exists():
            try:
                data = json.loads(metadata_file.read_text())
                for session_id, share_data in data.items():
                    self._shares[session_id] = ShareMetadata.from_dict(share_data)
                logger.info(f"Loaded {len(self._shares)} existing shares")
            except Exception as e:
                logger.error(f"Failed to load shares metadata: {e}")

    def _save_shares_metadata(self):
        """Save shares metadata to disk."""
        metadata_file = SHARES_DIR / "shares_metadata.json"
        try:
            data = {
                session_id: share.to_dict()
                for session_id, share in self._shares.items()
            }
            metadata_file.write_text(json.dumps(data, indent=2))
            logger.debug("Shares metadata saved")
        except Exception as e:
            logger.error(f"Failed to save shares metadata: {e}")

    def _generate_secret(self) -> str:
        """
        Generate a random secret for share authentication.

        Returns:
            URL-safe random secret (32 bytes)
        """
        return secrets.token_urlsafe(32)

    def _generate_share_key(self) -> str:
        """
        Generate a unique share key.

        Returns:
            UUID-based share key
        """
        return str(uuid.uuid4())

    def create_share(self, session_id: str) -> Tuple[str, str]:
        """
        Create a shareable URL and secret for a session.

        Args:
            session_id: Session ID to share

        Returns:
            Tuple of (share_url, secret)

        Example:
            url, secret = sharer.create_share("session_123")
            print(f"Share URL: {url}")
            print(f"Secret (keep private): {secret}")
        """
        # Check if share already exists
        if session_id in self._shares:
            share = self._shares[session_id]
            logger.info(f"Share already exists for session {session_id}")
            return self._build_share_url(share.share_key), share.secret

        # Generate new share
        secret = self._generate_secret()
        share_key = self._generate_share_key()

        share = ShareMetadata(
            session_id=session_id,
            secret=secret,
            share_key=share_key,
            created_at=datetime.now().isoformat()
        )

        self._shares[session_id] = share
        self._save_shares_metadata()

        share_url = self._build_share_url(share_key)

        logger.info(f"Created share for session {session_id}: {share_url}")
        return share_url, secret

    def _build_share_url(self, share_key: str) -> str:
        """
        Build share URL from share key.

        Args:
            share_key: Share key

        Returns:
            Full share URL
        """
        return f"{self.base_url}/shared/{share_key}"

    async def sync_session(self, session_id: str, session_data: Dict[str, Any]):
        """
        Sync full session data to share.

        Only syncs if a valid share exists for the session.
        Uses incremental updates to send only changes.

        Args:
            session_id: Session ID to sync
            session_data: Session data from SessionState.export_session()

        Example:
            from session_state import SessionState

            session = SessionState()
            # ... use session ...

            data = session.export_session()
            await sharer.sync_session(session.session_id, data)
        """
        # Only sync if share exists
        if session_id not in self._shares:
            logger.debug(f"No share exists for session {session_id}, skipping sync")
            return

        # Create sync task
        task = SyncTask(
            session_id=session_id,
            task_type="full_session",
            payload=session_data
        )

        # Add to pending and queue
        self._pending_syncs[session_id].append(task)
        await self._sync_queue.put(task)

        # Start processing if not already running
        if not self._processing:
            asyncio.create_task(self._process_sync_queue())

        logger.debug(f"Queued full session sync for {session_id}")

    async def sync_message(self, session_id: str, message_id: str, message_data: Dict[str, Any]):
        """
        Sync a single message update to share.

        Args:
            session_id: Session ID
            message_id: Message ID to sync
            message_data: Message data to sync

        Example:
            await sharer.sync_message(
                session_id="session_123",
                message_id="msg_456",
                message_data={
                    "timestamp": "2025-12-10T10:30:00",
                    "action": "click",
                    "success": True
                }
            )
        """
        # Only sync if share exists
        if session_id not in self._shares:
            logger.debug(f"No share exists for session {session_id}, skipping message sync")
            return

        # Create sync task
        task = SyncTask(
            session_id=session_id,
            task_type="message",
            payload={
                "message_id": message_id,
                "data": message_data
            }
        )

        # Add to pending and queue
        self._pending_syncs[session_id].append(task)
        await self._sync_queue.put(task)

        # Start processing if not already running
        if not self._processing:
            asyncio.create_task(self._process_sync_queue())

        logger.debug(f"Queued message sync for {session_id}/{message_id}")

    async def _process_sync_queue(self):
        """
        Process sync queue sequentially.

        Ensures syncs happen in order without race conditions.
        """
        self._processing = True

        try:
            while not self._sync_queue.empty():
                task = await self._sync_queue.get()

                try:
                    await self._execute_sync(task)
                except Exception as e:
                    logger.error(f"Failed to execute sync for {task.session_id}: {e}")
                finally:
                    self._sync_queue.task_done()
        finally:
            self._processing = False

    async def _execute_sync(self, task: SyncTask):
        """
        Execute a sync task.

        Args:
            task: SyncTask to execute
        """
        session_id = task.session_id
        share = self._shares.get(session_id)

        if not share:
            logger.warning(f"Share not found for session {session_id}, skipping sync")
            return

        # Determine what changed
        if task.task_type == "full_session":
            diff = self._compute_session_diff(share, task.payload)
            if diff:
                self._write_session_data(share, diff)
        elif task.task_type == "message":
            message_id = task.payload["message_id"]
            if message_id not in share.message_ids:
                self._write_message_data(share, message_id, task.payload["data"])
                share.message_ids.add(message_id)

        # Update sync metadata
        share.last_synced_at = datetime.now().isoformat()
        share.sync_count += 1
        self._save_shares_metadata()

        # Remove from pending
        if session_id in self._pending_syncs:
            self._pending_syncs[session_id] = [
                t for t in self._pending_syncs[session_id]
                if t.timestamp != task.timestamp
            ]

        logger.debug(f"Executed sync for {session_id} (type: {task.task_type})")

    def _compute_session_diff(self, share: ShareMetadata, session_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Compute diff between current share and new session data.

        Args:
            share: Current share metadata
            session_data: New session data

        Returns:
            Diff data or None if no changes
        """
        diff = {
            "session_id": share.session_id,
            "timestamp": datetime.now().isoformat(),
            "changes": {}
        }

        # Check for new messages
        messages = session_data.get('messages', [])
        new_messages = []
        for msg in messages:
            msg_id = msg.get('timestamp')  # Using timestamp as message ID
            if msg_id and msg_id not in share.message_ids:
                new_messages.append(msg)
                share.message_ids.add(msg_id)

        if new_messages:
            diff["changes"]["messages"] = new_messages

        # Check for stats changes
        diff["changes"]["stats"] = session_data.get('stats', {})
        diff["changes"]["timestamps"] = session_data.get('timestamps', {})
        diff["changes"]["goal"] = session_data.get('goal', {})

        # Return None if no meaningful changes
        if not new_messages and not diff["changes"]["stats"]:
            return None

        return diff

    def _write_session_data(self, share: ShareMetadata, diff: Dict[str, Any]):
        """
        Write session diff to share file.

        Args:
            share: Share metadata
            diff: Diff data to write
        """
        share_dir = SHARES_DIR / share.share_key
        share_dir.mkdir(exist_ok=True)

        # Append to session log
        session_file = share_dir / "session.jsonl"
        with session_file.open('a') as f:
            f.write(json.dumps(diff) + '\n')

        logger.debug(f"Wrote session diff for {share.session_id}")

    def _write_message_data(self, share: ShareMetadata, message_id: str, message_data: Dict[str, Any]):
        """
        Write message data to share file.

        Args:
            share: Share metadata
            message_id: Message ID
            message_data: Message data
        """
        share_dir = SHARES_DIR / share.share_key
        share_dir.mkdir(exist_ok=True)

        # Write to messages file
        messages_file = share_dir / "messages.jsonl"
        entry = {
            "message_id": message_id,
            "timestamp": datetime.now().isoformat(),
            "data": message_data
        }
        with messages_file.open('a') as f:
            f.write(json.dumps(entry) + '\n')

        logger.debug(f"Wrote message {message_id} for {share.session_id}")

    def delete_share(self, session_id: str) -> bool:
        """
        Delete a share and all its data.

        Args:
            session_id: Session ID to delete share for

        Returns:
            True if share was deleted, False if not found

        Example:
            deleted = sharer.delete_share("session_123")
            if deleted:
                print("Share deleted successfully")
        """
        if session_id not in self._shares:
            logger.warning(f"No share found for session {session_id}")
            return False

        share = self._shares[session_id]

        # Delete share directory
        share_dir = SHARES_DIR / share.share_key
        if share_dir.exists():
            import shutil
            shutil.rmtree(share_dir)

        # Remove from memory
        del self._shares[session_id]

        # Remove pending syncs
        if session_id in self._pending_syncs:
            del self._pending_syncs[session_id]

        self._save_shares_metadata()

        logger.info(f"Deleted share for session {session_id}")
        return True

    def get_share_url(self, session_id: str) -> Optional[str]:
        """
        Get share URL for a session.

        Args:
            session_id: Session ID

        Returns:
            Share URL or None if no share exists

        Example:
            url = sharer.get_share_url("session_123")
            if url:
                print(f"Share at: {url}")
        """
        share = self._shares.get(session_id)
        if share:
            return self._build_share_url(share.share_key)
        return None

    def get_session_info(self, share_key: str, secret: str) -> Optional[Dict[str, Any]]:
        """
        Get session info for a share key (with authentication).

        This would be called by a server endpoint: /session/info/{share_key}

        Args:
            share_key: Share key from URL
            secret: Secret for authentication

        Returns:
            Session info or None if invalid

        Example:
            info = sharer.get_session_info(share_key="abc123", secret=os.environ.get("SESSION_SECRET", "TEST_secret_placeholder"))
            if info:
                print(f"Session: {info['session_id']}")
        """
        # Find share by key
        share = None
        for s in self._shares.values():
            if s.share_key == share_key:
                share = s
                break

        if not share:
            logger.warning(f"Share not found: {share_key}")
            return None

        # Verify secret
        if share.secret != secret:
            logger.warning(f"Invalid secret for share {share_key}")
            return None

        # Read session data
        share_dir = SHARES_DIR / share.share_key
        session_file = share_dir / "session.jsonl"

        if not session_file.exists():
            return {
                "session_id": share.session_id,
                "created_at": share.created_at,
                "last_synced_at": share.last_synced_at,
                "sync_count": share.sync_count,
                "messages": [],
                "stats": {}
            }

        # Aggregate session data from diffs
        session_data = {
            "session_id": share.session_id,
            "created_at": share.created_at,
            "last_synced_at": share.last_synced_at,
            "sync_count": share.sync_count,
            "messages": [],
            "stats": {},
            "timestamps": {},
            "goal": {}
        }

        try:
            with session_file.open('r') as f:
                for line in f:
                    diff = json.loads(line)
                    changes = diff.get('changes', {})

                    # Merge messages
                    if 'messages' in changes:
                        session_data['messages'].extend(changes['messages'])

                    # Update stats (latest wins)
                    if 'stats' in changes:
                        session_data['stats'] = changes['stats']

                    # Update timestamps (latest wins)
                    if 'timestamps' in changes:
                        session_data['timestamps'] = changes['timestamps']

                    # Update goal (latest wins)
                    if 'goal' in changes:
                        session_data['goal'] = changes['goal']
        except Exception as e:
            logger.error(f"Failed to read session data: {e}")
            return None

        return session_data

    def get_message(self, share_key: str, message_id: str, secret: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific message from a share (with authentication).

        This would be called by a server endpoint: /session/message/{share_key}/{message_id}

        Args:
            share_key: Share key from URL
            message_id: Message ID to retrieve
            secret: Secret for authentication

        Returns:
            Message data or None if invalid
        """
        # Find and verify share
        share = None
        for s in self._shares.values():
            if s.share_key == share_key:
                share = s
                break

        if not share or share.secret != secret:
            logger.warning(f"Invalid share or secret for {share_key}")
            return None

        # Read messages file
        share_dir = SHARES_DIR / share.share_key
        messages_file = share_dir / "messages.jsonl"

        if not messages_file.exists():
            return None

        try:
            with messages_file.open('r') as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get('message_id') == message_id:
                        return entry.get('data')
        except Exception as e:
            logger.error(f"Failed to read message: {e}")
            return None

        return None

    def export_share(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Export share data with secret (for local backup).

        Args:
            session_id: Session ID to export

        Returns:
            Export data including secret

        Example:
            export = sharer.export_share("session_123")
            if export:
                # Save to file or send to another system
                with open('share_backup.json', 'w') as f:
                    json.dump(export, f, indent=2)
        """
        share = self._shares.get(session_id)
        if not share:
            return None

        # Get session info (using own secret)
        session_info = self.get_session_info(share.share_key, share.secret)

        return {
            "session_id": share.session_id,
            "secret": share.secret,
            "key": share.share_key,
            "created_at": share.created_at,
            "content": session_info
        }

    def list_shares(self) -> List[Dict[str, Any]]:
        """
        List all active shares.

        Returns:
            List of share summaries (without secrets)

        Example:
            shares = sharer.list_shares()
            for share in shares:
                print(f"{share['session_id']}: {share['share_url']}")
        """
        return [
            {
                "session_id": share.session_id,
                "share_url": self._build_share_url(share.share_key),
                "created_at": share.created_at,
                "last_synced_at": share.last_synced_at,
                "sync_count": share.sync_count,
                "message_count": len(share.message_ids)
            }
            for share in self._shares.values()
        ]

    def get_pending_syncs(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get pending sync tasks for a session.

        Args:
            session_id: Session ID

        Returns:
            List of pending sync tasks
        """
        tasks = self._pending_syncs.get(session_id, [])
        return [
            {
                "task_type": task.task_type,
                "timestamp": task.timestamp
            }
            for task in tasks
        ]


# Test code
if __name__ == "__main__":
    import asyncio

    async def run_tests():
        print("=" * 60)
        print("Session Sharing System Tests")
        print("=" * 60)
        print()

        # Initialize sharer
        sharer = SessionSharer(base_url="https://eversale.io")

        # Test 1: Create share
        print("Test 1: Create Share")
        session_id = "test_session_" + str(uuid.uuid4())
        share_url, secret = sharer.create_share(session_id)
        print(f"  Session ID: {session_id}")
        print(f"  Share URL: {share_url}")
        print(f"  Secret: {secret}")
        print(f"  SUCCESS\n")

        # Test 2: Sync session data
        print("Test 2: Sync Session Data")
        session_data = {
            "session_id": session_id,
            "messages": [
                {
                    "timestamp": "2025-12-10T10:00:00",
                    "action": "click",
                    "success": True
                },
                {
                    "timestamp": "2025-12-10T10:01:00",
                    "action": "type",
                    "success": True
                }
            ],
            "stats": {
                "iterations": 5,
                "tool_calls": 10,
                "retries": 2
            },
            "timestamps": {
                "task_start": "2025-12-10T09:59:00",
                "duration_seconds": 120
            },
            "goal": {
                "summary": "Test automation task",
                "keywords": ["test", "automation"]
            }
        }
        await sharer.sync_session(session_id, session_data)

        # Wait for sync to complete
        await asyncio.sleep(0.5)

        print(f"  Synced {len(session_data['messages'])} messages")
        print(f"  SUCCESS\n")

        # Test 3: Sync additional message
        print("Test 3: Sync Additional Message")
        await sharer.sync_message(
            session_id=session_id,
            message_id="msg_001",
            message_data={
                "timestamp": "2025-12-10T10:02:00",
                "action": "navigate",
                "success": True
            }
        )

        # Wait for sync to complete
        await asyncio.sleep(0.5)

        print(f"  Synced individual message")
        print(f"  SUCCESS\n")

        # Test 4: Get share info
        print("Test 4: Get Share Info")
        share_key = share_url.split('/')[-1]
        info = sharer.get_session_info(share_key, secret)
        if info:
            print(f"  Session ID: {info['session_id']}")
            print(f"  Message count: {len(info['messages'])}")
            print(f"  Stats: {info['stats']}")
            print(f"  SUCCESS\n")
        else:
            print(f"  FAILED - Could not retrieve share info\n")

        # Test 5: Get share URL
        print("Test 5: Get Share URL")
        url = sharer.get_share_url(session_id)
        if url == share_url:
            print(f"  URL: {url}")
            print(f"  SUCCESS\n")
        else:
            print(f"  FAILED - URL mismatch\n")

        # Test 6: List shares
        print("Test 6: List Shares")
        shares = sharer.list_shares()
        print(f"  Found {len(shares)} share(s)")
        for share in shares:
            print(f"    - {share['session_id']}: {share['message_count']} messages")
        print(f"  SUCCESS\n")

        # Test 7: Export share
        print("Test 7: Export Share")
        export = sharer.export_share(session_id)
        if export:
            print(f"  Exported session: {export['session_id']}")
            print(f"  Share key: {export['key']}")
            print(f"  Has secret: {bool(export['secret'])}")
            print(f"  SUCCESS\n")
        else:
            print(f"  FAILED - Could not export share\n")

        # Test 8: Invalid secret authentication
        print("Test 8: Invalid Secret Authentication")
        invalid_info = sharer.get_session_info(share_key, "invalid_secret")
        if invalid_info is None:
            print(f"  Correctly rejected invalid secret")
            print(f"  SUCCESS\n")
        else:
            print(f"  FAILED - Should have rejected invalid secret\n")

        # Test 9: Delete share
        print("Test 9: Delete Share")
        deleted = sharer.delete_share(session_id)
        if deleted:
            print(f"  Share deleted successfully")
            remaining_shares = sharer.list_shares()
            print(f"  Remaining shares: {len(remaining_shares)}")
            print(f"  SUCCESS\n")
        else:
            print(f"  FAILED - Could not delete share\n")

        # Test 10: Verify share is gone
        print("Test 10: Verify Share Deleted")
        url_after_delete = sharer.get_share_url(session_id)
        if url_after_delete is None:
            print(f"  Share URL no longer available")
            print(f"  SUCCESS\n")
        else:
            print(f"  FAILED - Share still exists after deletion\n")

        print("=" * 60)
        print("All Tests Completed")
        print("=" * 60)

    # Run tests
    asyncio.run(run_tests())
