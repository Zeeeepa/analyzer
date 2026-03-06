"""
Playbook storage and retrieval system for learned strategies.
Keeps playbook small and relevant by tracking success rates and pruning low-value entries.
"""

import yaml
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from pathlib import Path
from loguru import logger
from datetime import datetime


@dataclass
class Strategy:
    """A learned strategy with success tracking."""
    domain: str  # e.g., 'linkedin.com', 'facebook.com/ads/library'
    action_type: str  # e.g., 'search', 'extract_contacts', 'handle_popup'
    strategy: str  # The actual learned pattern (natural language)
    marker: str  # '✓' (helpful), '✗' (harmful), '○' (neutral)
    success_count: int = 0
    failure_count: int = 0
    created_at: str = ""
    last_used: str = ""
    page_type: str = "general"  # Sub-classification: 'sales_navigator', 'recruiter', 'regular_search', etc.

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5  # Default to neutral

    def record_outcome(self, success: bool):
        """Record a usage outcome to update success tracking."""
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.last_used = datetime.now().isoformat()


class Playbook:
    """
    Manages learned strategies with efficient storage and retrieval.
    Stores strategies by domain and action type for fast querying.
    """

    def __init__(self, filepath: Optional[Path] = None):
        self.filepath = filepath or Path("ace/playbook.yaml")
        self.strategies: List[Strategy] = []

        # Index for fast lookups
        self._index: Dict[str, List[Strategy]] = {}

        # Load existing playbook if it exists
        if self.filepath.exists():
            self.load()

    def _rebuild_index(self):
        """Rebuild the domain+action_type+page_type index for fast queries."""
        self._index.clear()
        for strategy in self.strategies:
            # Primary key: domain:action_type
            key = f"{strategy.domain}:{strategy.action_type}"
            if key not in self._index:
                self._index[key] = []
            self._index[key].append(strategy)

            # Secondary key with page_type for finer granularity
            page_type = getattr(strategy, 'page_type', 'general')
            if page_type != 'general':
                specific_key = f"{strategy.domain}:{strategy.action_type}:{page_type}"
                if specific_key not in self._index:
                    self._index[specific_key] = []
                self._index[specific_key].append(strategy)

    def load(self):
        """Load playbook from YAML file."""
        try:
            with open(self.filepath, 'r') as f:
                data = yaml.safe_load(f)

            if not data or 'strategies' not in data:
                logger.warning(f"Empty or invalid playbook at {self.filepath}")
                return

            self.strategies = [
                Strategy(**s) for s in data['strategies']
            ]
            self._rebuild_index()
            logger.info(f"Loaded {len(self.strategies)} strategies from playbook")

        except Exception as e:
            logger.error(f"Failed to load playbook: {e}")
            self.strategies = []

    def save(self):
        """Save playbook to YAML file."""
        try:
            # Ensure directory exists
            self.filepath.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'version': '1.0',
                'updated_at': datetime.now().isoformat(),
                'strategies': [asdict(s) for s in self.strategies]
            }

            with open(self.filepath, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            logger.debug(f"Saved {len(self.strategies)} strategies to playbook")

        except Exception as e:
            logger.error(f"Failed to save playbook: {e}")

    def query_strategies(
        self,
        domain: str,
        action_type: str,
        limit: int = 5,
        min_success_rate: float = 0.3,
        page_type: Optional[str] = None
    ) -> List[Strategy]:
        """
        Query relevant strategies for a domain and action type.
        Optionally filter by page_type for finer granularity (e.g., 'sales_navigator' vs 'regular_search').
        Returns top strategies sorted by success rate.
        """
        # Try specific page_type first if provided
        if page_type and page_type != 'general':
            specific_key = f"{domain}:{action_type}:{page_type}"
            specific_candidates = self._index.get(specific_key, [])

            if specific_candidates:
                # Filter by minimum success rate
                filtered = [s for s in specific_candidates if s.success_rate >= min_success_rate]

                # Sort by success rate (highest first)
                sorted_strategies = sorted(filtered, key=lambda s: s.success_rate, reverse=True)

                # Return if we have enough specific strategies
                if len(sorted_strategies) >= limit:
                    return sorted_strategies[:limit]

                # Otherwise fall through to get general strategies too

        # Get general strategies for this domain+action
        key = f"{domain}:{action_type}"
        candidates = self._index.get(key, [])

        # Filter by minimum success rate and exclude page-specific ones we already have
        if page_type:
            # Get the page-specific ones we already found
            specific_key = f"{domain}:{action_type}:{page_type}"
            specific_ids = {id(s) for s in self._index.get(specific_key, [])}
            filtered = [s for s in candidates
                       if s.success_rate >= min_success_rate
                       and id(s) not in specific_ids]
        else:
            filtered = [s for s in candidates if s.success_rate >= min_success_rate]

        # Sort by success rate (highest first)
        sorted_strategies = sorted(filtered, key=lambda s: s.success_rate, reverse=True)

        return sorted_strategies[:limit]

    def add_strategy(
        self,
        domain: str,
        action_type: str,
        strategy: str,
        marker: str = '✓',
        deduplicate: bool = True,
        page_type: str = "general"
    ) -> bool:
        """
        Add a new strategy to the playbook.
        Returns True if added, False if duplicate.
        """
        # Normalize strategy text for comparison
        normalized = strategy.lower().strip()

        if deduplicate:
            # Check for similar existing strategies
            key = f"{domain}:{action_type}"
            existing = self._index.get(key, [])

            for existing_strategy in existing:
                if existing_strategy.strategy.lower().strip() == normalized:
                    logger.debug(f"Strategy already exists: {strategy[:50]}...")
                    return False

        # Add new strategy
        new_strategy = Strategy(
            domain=domain,
            action_type=action_type,
            strategy=strategy,
            marker=marker,
            page_type=page_type
        )

        self.strategies.append(new_strategy)

        # Update index
        key = f"{domain}:{action_type}"
        if key not in self._index:
            self._index[key] = []
        self._index[key].append(new_strategy)

        logger.info(f"Added strategy for {domain}/{action_type}: {strategy[:50]}...")
        return True

    def prune_low_value_strategies(
        self,
        min_success_rate: float = 0.2,
        min_usage_count: int = 3
    ):
        """
        Remove strategies with low success rates or insufficient data.
        Only prunes strategies that have been tried multiple times.
        """
        original_count = len(self.strategies)

        self.strategies = [
            s for s in self.strategies
            if (s.success_count + s.failure_count < min_usage_count) or
               (s.success_rate >= min_success_rate)
        ]

        pruned_count = original_count - len(self.strategies)

        if pruned_count > 0:
            logger.info(f"Pruned {pruned_count} low-value strategies")
            self._rebuild_index()

        return pruned_count

    def get_stats(self) -> Dict:
        """Get playbook statistics."""
        total = len(self.strategies)

        if total == 0:
            return {
                'total_strategies': 0,
                'avg_success_rate': 0.0,
                'domains': [],
                'action_types': []
            }

        domains = set(s.domain for s in self.strategies)
        action_types = set(s.action_type for s in self.strategies)
        avg_success = sum(s.success_rate for s in self.strategies) / total

        return {
            'total_strategies': total,
            'avg_success_rate': round(avg_success, 3),
            'domains': sorted(domains),
            'action_types': sorted(action_types)
        }
