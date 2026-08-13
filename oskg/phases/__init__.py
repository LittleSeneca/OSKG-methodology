"""Phase drivers, one per pipeline stage.

Every driver subclasses `Phase` (see `base.py`), which owns the machinery they
share: budget admission control, prompt rendering, gate-and-repair, state
updates, and the per-phase commit. A driver only has to answer two questions —
what work is outstanding, and how does one batch of it become a prompt.
"""

from .base import Phase, PhaseOutcome
from .phase0 import ScopingPhase
from .phase1 import ReadingNotesPhase
from .phase2 import ClaimsPhase
from .phase3 import EdgesPhase
from .phase4 import SynthesisPhase
from .phase5 import CapstonePhase

PHASE_CLASSES = {
    0: ScopingPhase,
    1: ReadingNotesPhase,
    2: ClaimsPhase,
    3: EdgesPhase,
    4: SynthesisPhase,
    5: CapstonePhase,
}

__all__ = ["Phase", "PhaseOutcome", "PHASE_CLASSES"] + [c.__name__ for c in PHASE_CLASSES.values()]
