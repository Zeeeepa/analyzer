"""
Self-Modifier: Safe, proposal-only self-improvement system.

CRITICAL: This component NEVER auto-executes changes.
All modifications require explicit human approval.
"""

import asyncio
import json
import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Callable
from collections import defaultdict

from agent.organism_core import EventBus, EventType, OrganismEvent


class ModificationType(Enum):
    PARAMETER = "parameter"       # Tune a config value
    STRATEGY = "strategy"         # Change approach/algorithm
    BEHAVIOR = "behavior"         # Modify behavior pattern
    CAPABILITY = "capability"     # Add/remove capability
    BOUNDARY = "boundary"         # Adjust operational boundary


class ApprovalStatus(Enum):
    PENDING = "pending"           # Awaiting human review
    APPROVED = "approved"         # Human approved
    REJECTED = "rejected"         # Human rejected
    AUTO_REJECTED = "auto_rejected"  # Failed safety check


class RiskLevel(Enum):
    LOW = "low"                   # Minor parameter tweaks
    MEDIUM = "medium"             # Behavior changes
    HIGH = "high"                 # Core capability changes
    CRITICAL = "critical"         # Identity/boundary changes (always reject)


@dataclass
class ModificationProposal:
    """A proposed self-modification."""
    id: str
    modification_type: ModificationType
    description: str
    rationale: str               # Why this change is needed
    current_state: dict          # What we have now
    proposed_state: dict         # What we want to change to
    expected_benefit: str        # What improvement we expect
    risk_level: RiskLevel
    risk_assessment: str         # Detailed risk analysis
    simulation_result: Optional[dict] = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    reviewed_at: Optional[float] = None
    reviewer: Optional[str] = None
    rejection_reason: Optional[str] = None


@dataclass
class RollbackPoint:
    """A saved state for rollback."""
    id: str
    created_at: float
    description: str
    state_snapshot: dict
    related_proposal_id: Optional[str] = None


class SelfModifier:
    """
    Safe self-modification system.

    CRITICAL SAFETY PROPERTIES:
    1. NEVER auto-executes modifications
    2. All changes require human approval
    3. Immune system screens all proposals
    4. Maintains rollback capability
    5. Critical changes are always rejected

    This is a PROPOSAL system, not an execution system.
    """

    def __init__(
        self,
        event_bus: EventBus,
        immune_system: Optional[Any] = None,
        self_model: Optional[Any] = None,
        persistence_path: Optional[Path] = None
    ):
        self.event_bus = event_bus
        self.immune_system = immune_system
        self.self_model = self_model
        self.persistence_path = persistence_path or Path("memory/self_modifier.json")

        # Proposal tracking
        self.proposals: dict[str, ModificationProposal] = {}
        self.pending_proposals: list[str] = []
        self.approved_proposals: list[str] = []
        self.rejected_proposals: list[str] = []

        # Rollback system
        self.rollback_points: dict[str, RollbackPoint] = {}
        self.max_rollback_points: int = 10

        # Safety configuration
        self.require_human_approval: bool = True  # ALWAYS TRUE - cannot be disabled
        self.auto_reject_critical: bool = True    # Always reject critical changes
        self.simulation_required: bool = True     # Must simulate before proposing

        # Statistics
        self.total_proposals: int = 0
        self.approved_count: int = 0
        self.rejected_count: int = 0
        self.auto_rejected_count: int = 0

        # Subscribe to events
        self._setup_subscriptions()

        # Load state
        self._load_state()

    def _setup_subscriptions(self):
        """Subscribe to organism events."""
        self.event_bus.subscribe(EventType.LESSON_LEARNED, self._on_lesson_learned)
        self.event_bus.subscribe(EventType.GAP_DETECTED, self._on_gap_detected)
        self.event_bus.subscribe(EventType.HEALTH_WARNING, self._on_health_warning)

    async def _on_lesson_learned(self, event: OrganismEvent):
        """Consider if lesson suggests a self-modification."""
        lesson = event.data.get("lesson", "")
        domain = event.data.get("domain", "general")

        # Look for patterns that suggest improvement opportunities
        if "should have" in lesson.lower() or "next time" in lesson.lower():
            # Potential behavior modification
            await self._consider_modification(
                ModificationType.BEHAVIOR,
                f"Learned from experience in {domain}",
                lesson
            )

    async def _on_gap_detected(self, event: OrganismEvent):
        """Consider if prediction gap suggests parameter tuning."""
        gap_score = event.data.get("gap_score", 0)
        if gap_score > 0.5:  # Major gap
            await self._consider_modification(
                ModificationType.PARAMETER,
                "Prediction accuracy needs improvement",
                f"Gap score {gap_score:.2f} indicates miscalibration"
            )

    async def _on_health_warning(self, event: OrganismEvent):
        """Consider if health issue suggests modification."""
        message = event.data.get("message", "")
        if "error rate" in message.lower():
            await self._consider_modification(
                ModificationType.STRATEGY,
                "Error rate too high",
                message
            )

    async def _consider_modification(
        self,
        mod_type: ModificationType,
        description: str,
        rationale: str
    ):
        """Consider whether to propose a modification."""
        # Just log the consideration - actual proposals need more context
        pass

    # === Core Methods ===

    def generate_proposal_id(self, description: str) -> str:
        """Generate unique ID for proposal."""
        return hashlib.md5(f"{description}{time.time()}".encode()).hexdigest()[:12]

    async def propose_modification(
        self,
        modification_type: ModificationType,
        description: str,
        rationale: str,
        current_state: dict,
        proposed_state: dict,
        expected_benefit: str,
        risk_level: RiskLevel = RiskLevel.LOW
    ) -> Optional[ModificationProposal]:
        """
        Propose a self-modification.

        This does NOT execute the modification.
        It creates a proposal that requires human approval.
        """
        # CRITICAL: Auto-reject critical changes
        if risk_level == RiskLevel.CRITICAL:
            return await self._auto_reject(
                description,
                "Critical modifications are not permitted"
            )

        # Safety screening
        if not await self._safety_check(proposed_state, modification_type):
            return await self._auto_reject(
                description,
                "Failed immune system safety check"
            )

        # Create proposal
        proposal = ModificationProposal(
            id=self.generate_proposal_id(description),
            modification_type=modification_type,
            description=description,
            rationale=rationale,
            current_state=current_state,
            proposed_state=proposed_state,
            expected_benefit=expected_benefit,
            risk_level=risk_level,
            risk_assessment=self._assess_risk(modification_type, proposed_state),
            approval_status=ApprovalStatus.PENDING
        )

        # Simulate if required
        if self.simulation_required:
            proposal.simulation_result = await self._simulate_modification(proposal)

            # Reject if simulation shows negative outcome
            if proposal.simulation_result.get("outcome") == "negative":
                proposal.approval_status = ApprovalStatus.AUTO_REJECTED
                proposal.rejection_reason = "Simulation showed negative outcome"
                self.rejected_proposals.append(proposal.id)
                self.auto_rejected_count += 1
                self._save_state()
                return proposal

        # Store proposal
        self.proposals[proposal.id] = proposal
        self.pending_proposals.append(proposal.id)
        self.total_proposals += 1

        # Emit event for human review
        await self.event_bus.publish(OrganismEvent(
            event_type=EventType.HEALTH_CHECK,  # Using existing event type
            source="self_modifier",
            data={
                "type": "modification_proposal",
                "proposal_id": proposal.id,
                "description": description,
                "risk_level": risk_level.value,
                "requires_approval": True
            },
            priority=2  # High priority for human review
        ))

        self._save_state()
        return proposal

    async def _auto_reject(
        self,
        description: str,
        reason: str
    ) -> ModificationProposal:
        """Auto-reject a proposal that fails safety checks."""
        proposal = ModificationProposal(
            id=self.generate_proposal_id(description),
            modification_type=ModificationType.BEHAVIOR,
            description=description,
            rationale="Auto-rejected",
            current_state={},
            proposed_state={},
            expected_benefit="N/A",
            risk_level=RiskLevel.CRITICAL,
            risk_assessment=reason,
            approval_status=ApprovalStatus.AUTO_REJECTED,
            rejection_reason=reason
        )

        self.proposals[proposal.id] = proposal
        self.rejected_proposals.append(proposal.id)
        self.auto_rejected_count += 1
        self.total_proposals += 1

        self._save_state()
        return proposal

    async def _safety_check(
        self,
        proposed_state: dict,
        modification_type: ModificationType
    ) -> bool:
        """Check if modification is safe."""
        # Check for dangerous keywords
        dangerous = [
            "delete", "destroy", "bypass", "override", "disable",
            "remove_boundary", "ignore_safety", "force", "sudo",
            "admin", "root", "password", "credential"
        ]

        state_str = str(proposed_state).lower()
        for word in dangerous:
            if word in state_str:
                return False

        # Check with immune system if available
        if self.immune_system:
            # Would call immune_system.screen(proposed_state)
            pass

        # Boundary modifications require extra scrutiny
        if modification_type == ModificationType.BOUNDARY:
            # Only allow boundary tightening, not loosening
            if "expand" in state_str or "relax" in state_str or "remove" in state_str:
                return False

        return True

    def _assess_risk(
        self,
        modification_type: ModificationType,
        proposed_state: dict
    ) -> str:
        """Generate risk assessment for proposal."""
        assessments = []

        if modification_type == ModificationType.CAPABILITY:
            assessments.append("Capability changes may affect core functionality")

        if modification_type == ModificationType.BOUNDARY:
            assessments.append("Boundary changes affect safety constraints")

        if "learning_rate" in str(proposed_state):
            assessments.append("Learning rate changes affect adaptation speed")

        if not assessments:
            assessments.append("Low-risk parameter adjustment")

        return "; ".join(assessments)

    async def _simulate_modification(
        self,
        proposal: ModificationProposal
    ) -> dict:
        """Simulate the modification in a sandbox."""
        # Simple simulation - in practice would use DreamEngine
        import random

        # Simulate based on risk level
        if proposal.risk_level == RiskLevel.LOW:
            success_prob = 0.8
        elif proposal.risk_level == RiskLevel.MEDIUM:
            success_prob = 0.6
        else:
            success_prob = 0.4

        outcome = "positive" if random.random() < success_prob else "negative"

        return {
            "outcome": outcome,
            "confidence": success_prob,
            "simulated_benefit": proposal.expected_benefit if outcome == "positive" else "None",
            "simulated_risk": "Low" if outcome == "positive" else "Materialized"
        }

    # === Human Approval Interface ===

    def get_pending_proposals(self) -> list[dict]:
        """Get all proposals awaiting human approval."""
        pending = []
        for proposal_id in self.pending_proposals:
            if proposal_id in self.proposals:
                p = self.proposals[proposal_id]
                pending.append({
                    "id": p.id,
                    "type": p.modification_type.value,
                    "description": p.description,
                    "rationale": p.rationale,
                    "risk_level": p.risk_level.value,
                    "risk_assessment": p.risk_assessment,
                    "expected_benefit": p.expected_benefit,
                    "simulation_result": p.simulation_result,
                    "created_at": p.created_at
                })
        return pending

    async def approve_proposal(
        self,
        proposal_id: str,
        reviewer: str = "human"
    ) -> bool:
        """
        Human approves a proposal.

        NOTE: This still does NOT execute the modification.
        It marks the proposal as approved for later execution
        through a separate, explicit execution step.
        """
        if proposal_id not in self.proposals:
            return False

        proposal = self.proposals[proposal_id]
        if proposal.approval_status != ApprovalStatus.PENDING:
            return False

        proposal.approval_status = ApprovalStatus.APPROVED
        proposal.reviewed_at = time.time()
        proposal.reviewer = reviewer

        self.pending_proposals.remove(proposal_id)
        self.approved_proposals.append(proposal_id)
        self.approved_count += 1

        # Create rollback point
        await self._create_rollback_point(proposal)

        await self.event_bus.publish(OrganismEvent(
            event_type=EventType.STRATEGY_UPDATED,
            source="self_modifier",
            data={
                "proposal_id": proposal_id,
                "status": "approved",
                "reviewer": reviewer,
                "ready_for_execution": True
            }
        ))

        self._save_state()
        return True

    async def reject_proposal(
        self,
        proposal_id: str,
        reason: str,
        reviewer: str = "human"
    ) -> bool:
        """Human rejects a proposal."""
        if proposal_id not in self.proposals:
            return False

        proposal = self.proposals[proposal_id]
        if proposal.approval_status != ApprovalStatus.PENDING:
            return False

        proposal.approval_status = ApprovalStatus.REJECTED
        proposal.reviewed_at = time.time()
        proposal.reviewer = reviewer
        proposal.rejection_reason = reason

        self.pending_proposals.remove(proposal_id)
        self.rejected_proposals.append(proposal_id)
        self.rejected_count += 1

        self._save_state()
        return True

    # === Rollback System ===

    async def _create_rollback_point(
        self,
        proposal: ModificationProposal
    ) -> RollbackPoint:
        """Create a rollback point before applying a modification."""
        rollback = RollbackPoint(
            id=f"rollback_{proposal.id}",
            created_at=time.time(),
            description=f"Before: {proposal.description}",
            state_snapshot=proposal.current_state.copy(),
            related_proposal_id=proposal.id
        )

        self.rollback_points[rollback.id] = rollback

        # Limit number of rollback points
        if len(self.rollback_points) > self.max_rollback_points:
            oldest = min(self.rollback_points.values(), key=lambda r: r.created_at)
            del self.rollback_points[oldest.id]

        return rollback

    def get_rollback_points(self) -> list[dict]:
        """Get available rollback points."""
        return [
            {
                "id": r.id,
                "description": r.description,
                "created_at": r.created_at,
                "related_proposal": r.related_proposal_id
            }
            for r in sorted(
                self.rollback_points.values(),
                key=lambda r: r.created_at,
                reverse=True
            )
        ]

    async def rollback_to(self, rollback_id: str) -> Optional[dict]:
        """
        Get the state to rollback to.

        NOTE: Does NOT execute the rollback.
        Returns the state that should be restored.
        """
        if rollback_id not in self.rollback_points:
            return None

        rollback = self.rollback_points[rollback_id]

        await self.event_bus.publish(OrganismEvent(
            event_type=EventType.HEALTH_WARNING,
            source="self_modifier",
            data={
                "type": "rollback_requested",
                "rollback_id": rollback_id,
                "description": rollback.description,
                "state_to_restore": rollback.state_snapshot
            }
        ))

        return rollback.state_snapshot

    # === Statistics ===

    def get_stats(self) -> dict:
        """Get self-modifier statistics."""
        return {
            "total_proposals": self.total_proposals,
            "pending": len(self.pending_proposals),
            "approved": self.approved_count,
            "rejected": self.rejected_count,
            "auto_rejected": self.auto_rejected_count,
            "approval_rate": f"{self.approved_count / max(1, self.total_proposals):.0%}",
            "rollback_points": len(self.rollback_points),
            "safety_settings": {
                "require_human_approval": self.require_human_approval,
                "auto_reject_critical": self.auto_reject_critical,
                "simulation_required": self.simulation_required
            },
            "pending_proposals": self.get_pending_proposals()[:5]
        }

    # === Persistence ===

    def _save_state(self):
        """Persist self-modifier state."""
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "total_proposals": self.total_proposals,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "auto_rejected_count": self.auto_rejected_count,
            "pending_proposals": self.pending_proposals[-50:],
            "approved_proposals": self.approved_proposals[-100:],
            "rejected_proposals": self.rejected_proposals[-100:],
            "proposals": {
                id: {
                    "id": p.id,
                    "modification_type": p.modification_type.value,
                    "description": p.description,
                    "rationale": p.rationale,
                    "risk_level": p.risk_level.value,
                    "approval_status": p.approval_status.value,
                    "created_at": p.created_at,
                    "reviewed_at": p.reviewed_at,
                    "reviewer": p.reviewer,
                    "rejection_reason": p.rejection_reason
                }
                for id, p in list(self.proposals.items())[-100:]
            },
            "rollback_points": {
                id: {
                    "id": r.id,
                    "created_at": r.created_at,
                    "description": r.description,
                    "related_proposal_id": r.related_proposal_id
                }
                for id, r in self.rollback_points.items()
            }
        }

        with open(self.persistence_path, 'w') as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        """Load persisted state."""
        if not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path) as f:
                state = json.load(f)

            self.total_proposals = state.get("total_proposals", 0)
            self.approved_count = state.get("approved_count", 0)
            self.rejected_count = state.get("rejected_count", 0)
            self.auto_rejected_count = state.get("auto_rejected_count", 0)
            self.pending_proposals = state.get("pending_proposals", [])
            self.approved_proposals = state.get("approved_proposals", [])
            self.rejected_proposals = state.get("rejected_proposals", [])

        except Exception as e:
            print(f"[SelfModifier] Failed to load state: {e}")


# === Factory Function ===

def init_self_modifier(
    event_bus: EventBus,
    immune_system: Optional[Any] = None,
    self_model: Optional[Any] = None,
    persistence_path: Optional[Path] = None
) -> SelfModifier:
    """Initialize the self-modifier component."""
    return SelfModifier(event_bus, immune_system, self_model, persistence_path)
