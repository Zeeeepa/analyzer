import asyncio
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class RecordedActionType(Enum):
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    KEYPRESS = "keypress"
    HOVER = "hover"
    DRAG = "drag"


@dataclass
class RecordedAction:
    timestamp: float
    action_type: RecordedActionType
    target_selector: str
    target_mmid: Optional[str]
    target_text: Optional[str]
    target_attributes: Dict[str, str]
    value: Optional[str]
    page_url: str
    page_title: str
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None


@dataclass
class Recording:
    id: str
    goal: str
    start_time: datetime
    end_time: Optional[datetime]
    actions: List[RecordedAction] = field(default_factory=list)
    variables_detected: Dict[str, str] = field(default_factory=dict)


class ActionRecorder:
    """
    Records user performing task in browser.
    Generates replayable workflow with self-healing selectors.
    """

    INJECT_SCRIPT = '''
    (function() {
        window._eversaleRecorder = {
            actions: [],
            recording: false,

            getUniqueSelector: function(el) {
                // Priority: data-mmid > id > name > class path > xpath
                if (el.dataset.mmid) return `[data-mmid="${el.dataset.mmid}"]`;
                if (el.id) return `#${el.id}`;
                if (el.name) return `[name="${el.name}"]`;

                // Build class path
                let path = [];
                let current = el;
                while (current && current !== document.body) {
                    let selector = current.tagName.toLowerCase();
                    if (current.className) {
                        selector += '.' + current.className.trim().split(/\\s+/).join('.');
                    }
                    path.unshift(selector);
                    current = current.parentElement;
                }
                return path.join(' > ');
            },

            getElementInfo: function(el) {
                return {
                    selector: this.getUniqueSelector(el),
                    mmid: el.dataset.mmid || null,
                    tag: el.tagName.toLowerCase(),
                    text: el.innerText?.slice(0, 100) || null,
                    value: el.value || null,
                    type: el.type || null,
                    placeholder: el.placeholder || null,
                    ariaLabel: el.getAttribute('aria-label') || null
                };
            },

            recordAction: function(type, event, value) {
                if (!this.recording) return;

                const el = event.target;
                const info = this.getElementInfo(el);

                this.actions.push({
                    timestamp: Date.now(),
                    type: type,
                    target: info,
                    value: value,
                    url: window.location.href,
                    title: document.title
                });

                // Notify Python side
                if (window._eversaleRecorderCallback) {
                    window._eversaleRecorderCallback(JSON.stringify(this.actions[this.actions.length - 1]));
                }
            },

            start: function() {
                this.recording = true;
                this.actions = [];

                // Click handler
                document.addEventListener('click', (e) => {
                    this.recordAction('click', e, null);
                }, true);

                // Input handler (debounced)
                let inputTimeout = null;
                document.addEventListener('input', (e) => {
                    clearTimeout(inputTimeout);
                    inputTimeout = setTimeout(() => {
                        this.recordAction('fill', e, e.target.value);
                    }, 500);
                }, true);

                // Select handler
                document.addEventListener('change', (e) => {
                    if (e.target.tagName === 'SELECT') {
                        this.recordAction('select', e, e.target.value);
                    }
                }, true);

                // Navigation detection
                const observer = new MutationObserver(() => {
                    if (window._lastUrl !== window.location.href) {
                        window._lastUrl = window.location.href;
                        this.actions.push({
                            timestamp: Date.now(),
                            type: 'navigate',
                            target: null,
                            value: window.location.href,
                            url: window.location.href,
                            title: document.title
                        });
                    }
                });
                observer.observe(document.body, { childList: true, subtree: true });
                window._lastUrl = window.location.href;

                console.log('[Eversale] Recording started');
            },

            stop: function() {
                this.recording = false;
                console.log('[Eversale] Recording stopped:', this.actions.length, 'actions');
                return this.actions;
            }
        };
    })();
    '''

    def __init__(self, mcp_client):
        self.mcp = mcp_client
        self.current_recording: Optional[Recording] = None
        self.recordings: List[Recording] = []

    async def start_recording(self, goal: str) -> str:
        """Start recording user actions."""
        import uuid

        recording_id = str(uuid.uuid4())[:8]
        self.current_recording = Recording(
            id=recording_id,
            goal=goal,
            start_time=datetime.now(),
            end_time=None
        )

        # Inject recording script
        await self.mcp.call_tool('playwright_evaluate', {
            'script': self.INJECT_SCRIPT
        })

        # Start recording
        await self.mcp.call_tool('playwright_evaluate', {
            'script': 'window._eversaleRecorder.start();'
        })

        # Set up callback for real-time action capture
        await self._setup_action_callback()

        print(f"[Recorder] Started recording: {recording_id}")
        print(f"[Recorder] Goal: {goal}")
        print("[Recorder] Perform your task in the browser. Press Ctrl+C when done.")

        return recording_id

    async def stop_recording(self) -> Recording:
        """Stop recording and return recorded actions."""
        if not self.current_recording:
            raise ValueError("No recording in progress")

        # Get final actions from browser
        result = await self.mcp.call_tool('playwright_evaluate', {
            'script': 'JSON.stringify(window._eversaleRecorder.stop())'
        })

        browser_actions = json.loads(result.get('result', '[]'))

        # Convert to RecordedAction objects
        for action in browser_actions:
            self.current_recording.actions.append(RecordedAction(
                timestamp=action['timestamp'],
                action_type=RecordedActionType(action['type']),
                target_selector=action['target']['selector'] if action['target'] else None,
                target_mmid=action['target']['mmid'] if action['target'] else None,
                target_text=action['target']['text'] if action['target'] else None,
                target_attributes={
                    'tag': action['target']['tag'] if action['target'] else None,
                    'type': action['target']['type'] if action['target'] else None,
                    'placeholder': action['target']['placeholder'] if action['target'] else None
                },
                value=action['value'],
                page_url=action['url'],
                page_title=action['title']
            ))

        self.current_recording.end_time = datetime.now()
        recording = self.current_recording
        self.recordings.append(recording)
        self.current_recording = None

        print(f"[Recorder] Stopped. Captured {len(recording.actions)} actions.")
        return recording

    async def _setup_action_callback(self):
        """Set up real-time action callback from browser."""
        # This would use CDP to get events in real-time
        # For now, we batch at the end
        pass
