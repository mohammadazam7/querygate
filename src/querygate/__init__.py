"""A SQL firewall for AI agents.

Model-written SQL goes through :func:`check` before it reaches a database. The query
must parse as one read-only statement, read only tables the policy allows, stay away
from denied columns, and carry a row limit.
"""

from querygate.gate import Checked, Policy, Refused, Rule, check

__all__ = ["Checked", "Policy", "Refused", "Rule", "check"]
__version__ = "0.1.2"
