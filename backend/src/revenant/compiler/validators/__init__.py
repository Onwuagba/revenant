"""Validators package: V1-V8 plus run_all.

Each validator returns ``ValidationResult{validator, passed, violations[]}``.
``run_all`` runs every validator and returns all results (never stops early).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..planner import Machine, State, StateKind, TERMINAL_KINDS


@dataclass
class Violation:
    validator: str
    state_id: str = ""
    message: str = ""
    measured: int | None = None


@dataclass
class ValidationResult:
    validator: str
    passed: bool
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator": self.validator,
            "passed": self.passed,
            "violations": [
                {"state_id": v.state_id, "message": v.message, "measured": v.measured}
                for v in self.violations
            ],
        }


def run_all(machine: Machine, ir_ops: list | None = None,
            refused_op_ids: set[str] | None = None) -> list[ValidationResult]:
    """Run all validators and return every result (never stop at first failure)."""
    from .reachability import validate_reachability
    from .exits import validate_exits
    from .back import validate_back
    from .steps import validate_steps
    from .length import validate_length
    from .pin import validate_pin
    from .sms import validate_sms
    from .refusal_soundness import validate_refusal_soundness

    results = [
        validate_reachability(machine),
        validate_exits(machine),
        validate_back(machine),
        validate_steps(machine),
        validate_length(machine),
        validate_pin(machine),
        validate_sms(machine),
        validate_refusal_soundness(machine, refused_op_ids or set()),
    ]
    return results
