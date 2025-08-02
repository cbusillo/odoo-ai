#!/usr/bin/env python3
"""
Systematic Error Recovery Framework for Claude Agents

Provides resilient error handling, automatic retries, fallback strategies,
and recovery workflows for multi-agent systems.
"""

import json
import logging
from typing import Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Classification of error severity levels."""

    TRANSIENT = "transient"  # Temporary, retry immediately
    RETRYABLE = "retryable"  # Can retry with backoff
    FALLBACK = "fallback"  # Try alternative approach
    FATAL = "fatal"  # Cannot recover, fail task


class ErrorCategory(Enum):
    """Types of errors we handle."""

    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    PERMISSION = "permission"
    VALIDATION = "validation"
    RESOURCE_NOT_FOUND = "resource_not_found"
    AGENT_FAILURE = "agent_failure"
    MODEL_UNAVAILABLE = "model_unavailable"
    CONTEXT_LIMIT = "context_limit"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information about an error."""

    error_type: type[Exception]
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    agent: str | None = None
    task: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class RecoveryStrategy:
    """Defines how to recover from an error."""

    strategy_type: str  # "retry", "fallback", "escalate", "fail"
    delay: float | None = None
    max_retries: int = 3
    fallback_agent: str | None = None
    fallback_model: str | None = None
    custom_handler: Callable | None = None


class ErrorClassifier:
    """Classifies errors to determine appropriate recovery strategy."""

    # Error pattern mappings
    ERROR_PATTERNS = {
        # Rate limit errors
        r"rate.?limit|too.?many.?requests|429": (ErrorCategory.RATE_LIMIT, ErrorSeverity.RETRYABLE),
        r"quota.?exceeded|limit.?reached": (ErrorCategory.RATE_LIMIT, ErrorSeverity.RETRYABLE),
        # Timeout errors
        r"timeout|timed?.?out|deadline.?exceeded": (ErrorCategory.TIMEOUT, ErrorSeverity.RETRYABLE),
        r"took.?too.?long|response.?time": (ErrorCategory.TIMEOUT, ErrorSeverity.RETRYABLE),
        # Network errors
        r"connection.?error|network|unreachable": (ErrorCategory.NETWORK, ErrorSeverity.TRANSIENT),
        r"dns|resolve|socket": (ErrorCategory.NETWORK, ErrorSeverity.TRANSIENT),
        # Permission errors
        r"permission.?denied|unauthorized|forbidden|403": (ErrorCategory.PERMISSION, ErrorSeverity.FATAL),
        r"access.?denied|not.?allowed": (ErrorCategory.PERMISSION, ErrorSeverity.FATAL),
        # Resource errors
        r"not.?found|404|missing|does.?not.?exist": (ErrorCategory.RESOURCE_NOT_FOUND, ErrorSeverity.FALLBACK),
        r"file.?not.?found|path.?not.?found": (ErrorCategory.RESOURCE_NOT_FOUND, ErrorSeverity.FALLBACK),
        # Model errors
        r"model.?not.?available|model.?error": (ErrorCategory.MODEL_UNAVAILABLE, ErrorSeverity.FALLBACK),
        r"claude|gpt|sonnet|opus|haiku": (ErrorCategory.MODEL_UNAVAILABLE, ErrorSeverity.FALLBACK),
        # Context errors
        r"context.?too.?long|token.?limit|context.?window": (ErrorCategory.CONTEXT_LIMIT, ErrorSeverity.FALLBACK),
        r"maximum.?context|too.?many.?tokens": (ErrorCategory.CONTEXT_LIMIT, ErrorSeverity.FALLBACK),
    }

    @classmethod
    def classify(cls, error: Exception, context: dict | None = None) -> ErrorContext:
        """Classify an error and determine its category and severity."""
        error_msg = str(error).lower()
        error_type = type(error)

        # Check against known patterns
        for pattern, (category, severity) in cls.ERROR_PATTERNS.items():
            import re

            if re.search(pattern, error_msg, re.IGNORECASE):
                return ErrorContext(
                    error_type=error_type, message=str(error), category=category, severity=severity, metadata=context or {}
                )

        # Default classification
        return ErrorContext(
            error_type=error_type,
            message=str(error),
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.RETRYABLE,
            metadata=context or {},
        )


class RecoveryEngine:
    def __init__(self) -> None:
        self.recovery_strategies = self._initialize_strategies()
        self.error_history: list[ErrorContext] = []

    @staticmethod
    def _initialize_strategies() -> dict[ErrorCategory, RecoveryStrategy]:
        return {
            ErrorCategory.RATE_LIMIT: RecoveryStrategy(
                strategy_type="retry",
                delay=30.0,  # 30 second delay for rate limits
                max_retries=5,
            ),
            ErrorCategory.TIMEOUT: RecoveryStrategy(strategy_type="retry", delay=5.0),
            ErrorCategory.NETWORK: RecoveryStrategy(strategy_type="retry", delay=2.0),
            ErrorCategory.PERMISSION: RecoveryStrategy(
                strategy_type="fail"  # Cannot recover from permission errors
            ),
            ErrorCategory.RESOURCE_NOT_FOUND: RecoveryStrategy(strategy_type="fallback", max_retries=1),
            ErrorCategory.MODEL_UNAVAILABLE: RecoveryStrategy(
                strategy_type="fallback",
                fallback_model="haiku-3.5",  # Fallback to simpler model
            ),
            ErrorCategory.CONTEXT_LIMIT: RecoveryStrategy(
                strategy_type="fallback",
                fallback_agent="gpt",  # Offload to GPT for large context
            ),
            ErrorCategory.AGENT_FAILURE: RecoveryStrategy(strategy_type="fallback", max_retries=2),
            ErrorCategory.UNKNOWN: RecoveryStrategy(strategy_type="retry", delay=5.0, max_retries=2),
        }

    def get_recovery_strategy(self, error_context: ErrorContext) -> RecoveryStrategy:
        """Get the appropriate recovery strategy for an error."""
        return self.recovery_strategies.get(error_context.category, self.recovery_strategies[ErrorCategory.UNKNOWN])

    @staticmethod
    def calculate_backoff(retry_count: int, base_delay: float = 1.0) -> float:
        """Calculate exponential backoff with jitter."""
        import random

        # Exponential backoff: 2^retry * base_delay
        delay = min(300, base_delay * (2**retry_count))  # Cap at 5 minutes
        # Add jitter (±20%)
        jitter = delay * 0.2 * (random.random() - 0.5)
        return max(0.1, delay + jitter)

    def should_retry(self, error_context: ErrorContext, strategy: RecoveryStrategy) -> bool:
        """Determine if we should retry based on error context and strategy."""
        if strategy.strategy_type not in ["retry", "fallback"]:
            return False

        if error_context.retry_count >= strategy.max_retries:
            return False

        # Check error history for repeated failures
        recent_errors = [error for error in self.error_history[-10:] if error.category == error_context.category]
        if len(recent_errors) >= 5:
            logger.warning(f"Too many recent {error_context.category} errors, stopping retries")
            return False

        return True

    def record_error(self, error_context: ErrorContext):
        """Record error in history for pattern analysis."""
        self.error_history.append(error_context)
        # Keep only last 100 errors
        if len(self.error_history) > 100:
            self.error_history = self.error_history[-100:]


class AgentErrorHandler:
    def __init__(self) -> None:
        self.classifier = ErrorClassifier()
        self.recovery_engine = RecoveryEngine()
        self.fallback_chains = self._initialize_fallback_chains()

    @staticmethod
    def _initialize_fallback_chains() -> dict[str, list[str]]:
        """Define fallback chains for each agent."""
        return {
            # Performance analysis fallbacks
            "flash": ["inspector", "archer"],
            # Code quality fallbacks
            "inspector": ["archer", "general-purpose"],
            # Test writing fallbacks
            "scout": ["general-purpose"],
            # Frontend fallbacks
            "owl": ["general-purpose"],
            # Research fallbacks
            "archer": ["general-purpose"],
            # Complex reasoning fallbacks
            "debugger": ["gpt", "anthropic-engineer"],
            "planner": ["gpt", "anthropic-engineer"],
            # Refactoring fallbacks
            "refactor": ["general-purpose"],
            # Default fallback
            "default": ["general-purpose"],
        }

    def get_fallback_agent(self, failed_agent: str) -> str | None:
        """Get the next fallback agent in the chain."""
        chain = self.fallback_chains.get(failed_agent, self.fallback_chains["default"])
        return chain[0] if chain else None

    def handle_agent_error(self, error: Exception, agent: str, task: str, context: dict | None = None) -> dict[str, str]:
        """Handle an error from an agent task."""
        # Classify the error
        error_context = self.classifier.classify(error, context)
        error_context.agent = agent
        error_context.task = task

        # Get recovery strategy
        strategy = self.recovery_engine.get_recovery_strategy(error_context)

        # Record error
        self.recovery_engine.record_error(error_context)

        # Log error details
        logger.error(f"Agent {agent} failed on task '{task}': {error}")
        logger.info(f"Error classified as {error_context.category.value} with severity {error_context.severity.value}")

        # Build recovery response
        response = {
            "error": str(error),
            "category": error_context.category.value,
            "severity": error_context.severity.value,
            "recovery_strategy": strategy.strategy_type,
            "can_retry": self.recovery_engine.should_retry(error_context, strategy),
            "retry_delay": None,
            "fallback_agent": None,
            "fallback_model": None,
            "recommendations": [],
        }

        if strategy.strategy_type == "retry" and response["can_retry"]:
            delay = self.recovery_engine.calculate_backoff(error_context.retry_count, strategy.delay or 1.0)
            response["retry_delay"] = delay
            response["recommendations"].append(
                f"Retry after {delay:.1f} seconds (attempt {error_context.retry_count + 1}/{strategy.max_retries})"
            )

        elif strategy.strategy_type == "fallback":
            if strategy.fallback_agent:
                response["fallback_agent"] = strategy.fallback_agent
                response["recommendations"].append(f"Fallback to {strategy.fallback_agent} agent")
            elif strategy.fallback_model:
                response["fallback_model"] = strategy.fallback_model
                response["recommendations"].append(f"Fallback to {strategy.fallback_model} model")
            else:
                fallback = self.get_fallback_agent(agent)
                if fallback:
                    response["fallback_agent"] = fallback
                    response["recommendations"].append(f"Fallback to {fallback} agent")

        elif strategy.strategy_type == "fail":
            response["recommendations"].append("Cannot recover from this error - manual intervention required")

        return response


# Convenience functions for easy integration
error_handler = AgentErrorHandler()


def handle_agent_error(error: Exception, agent: str, task: str, context: dict | None = None) -> dict[str, str]:
    """Global error handler for agent tasks."""
    return error_handler.handle_agent_error(error, agent, task, context)


def classify_error(error: Exception) -> ErrorContext:
    """Classify an error to understand its nature."""
    return ErrorClassifier.classify(error)


def get_retry_delay(error: Exception, retry_count: int = 0) -> float:
    """Get appropriate retry delay for an error."""
    context = classify_error(error)
    strategy = error_handler.recovery_engine.get_recovery_strategy(context)
    if strategy.strategy_type == "retry":
        return error_handler.recovery_engine.calculate_backoff(retry_count, strategy.delay or 1.0)
    return 0.0


# Example usage patterns
if __name__ == "__main__":
    # Example 1: Rate limit error
    try:
        raise Exception("API rate limit exceeded: 429 Too Many Requests")
    except Exception as e:
        result = handle_agent_error(e, "archer", "search Odoo patterns")
        print("Rate limit recovery:", json.dumps(result, indent=2))

    # Example 2: Context too long
    try:
        raise Exception("Context window exceeded: maximum 200k tokens")
    except Exception as e:
        result = handle_agent_error(e, "inspector", "analyze large module")
        print("\nContext limit recovery:", json.dumps(result, indent=2))

    # Example 3: Agent failure
    try:
        raise Exception("Agent 'flash' failed to complete performance analysis")
    except Exception as e:
        result = handle_agent_error(e, "flash", "check performance")
        print("\nAgent failure recovery:", json.dumps(result, indent=2))
