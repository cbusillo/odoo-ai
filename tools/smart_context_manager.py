#!/usr/bin/env python3
"""
Smart Context Management for Odoo Agent System

Automatically selects optimal agents and models to preserve Claude rate limits
by intelligently offloading to GPT and using efficient models.

OPTIMIZATION GOAL: Minimize Claude token usage, not cost!
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class TaskComplexity(Enum):
    """Task complexity levels"""
    SIMPLE = "simple"      # Basic operations, single file
    MEDIUM = "medium"      # Standard development, multi-file
    COMPLEX = "complex"    # Architecture, performance, debugging


class ModelTier(Enum):
    """Claude model tiers"""
    HAIKU = "haiku-3.5"    # Fast, cheap ($0.80/$4)
    SONNET = "sonnet-4"    # Balanced ($3/$15) 
    OPUS = "opus-4"        # Powerful ($15/$75)


@dataclass
class TaskAnalysis:
    """Analysis results for a task"""
    complexity: TaskComplexity
    recommended_model: ModelTier
    recommended_agent: str
    confidence: float
    reasoning: List[str]
    estimated_tokens: str
    rate_limit_impact: str
    gpt_offload_recommended: bool


class SmartContextManager:
    """Manages context and routing for Odoo agent tasks"""
    
    def __init__(self):
        # Keywords that indicate task complexity
        self.simple_keywords = [
            "read", "write", "copy", "move", "status", "list", "find", 
            "search", "simple", "basic", "quick", "check", "get", "show"
        ]
        
        self.complex_keywords = [
            "architecture", "design", "performance", "optimization", "debug",
            "race condition", "deadlock", "bottleneck", "refactor", "migration",
            "bulk", "systematic", "analyze", "investigate", "troubleshoot"
        ]
        
        # Keywords that strongly suggest GPT offload
        self.gpt_offload_keywords = [
            "implement complete", "generate entire", "create full",
            "build comprehensive", "mass generation", "bulk creation",
            "following patterns", "based on examples", "using templates"
        ]
        
        # Agent specialties with default models
        self.agent_config = {
            "archer": {"default_model": ModelTier.HAIKU, "specialty": "odoo_research"},
            "scout": {"default_model": ModelTier.SONNET, "specialty": "testing"},
            "owl": {"default_model": ModelTier.SONNET, "specialty": "frontend"},
            "inspector": {"default_model": ModelTier.SONNET, "specialty": "code_quality"},
            "qc": {"default_model": ModelTier.SONNET, "specialty": "quality_control"},
            "dock": {"default_model": ModelTier.HAIKU, "specialty": "containers"},
            "shopkeeper": {"default_model": ModelTier.SONNET, "specialty": "shopify"},
            "refactor": {"default_model": ModelTier.OPUS, "specialty": "bulk_changes"},
            "flash": {"default_model": ModelTier.OPUS, "specialty": "performance"},
            "debugger": {"default_model": ModelTier.OPUS, "specialty": "debugging"},
            "planner": {"default_model": ModelTier.OPUS, "specialty": "architecture"},
            "gpt": {"default_model": ModelTier.OPUS, "specialty": "consultation"},
            "phoenix": {"default_model": ModelTier.OPUS, "specialty": "migration"}
        }
        
        # Task patterns for agent routing (pattern_key -> [agent_name, keywords...])
        self.task_patterns = {
            "scout": ["scout", "write test", "test case", "unit test", "tour test"],
            "owl": ["owl", "javascript", "js", "component", "owl.js", "css", "html"],
            "inspector": ["inspector", "code quality", "lint", "review", "style", "analyze quality"],
            "qc": ["qc", "quality audit", "quality control", "comprehensive review", "quality gate", "pre-commit check"],
            "dock": ["dock", "docker", "container", "restart", "deploy"],
            "shopkeeper": ["shopkeeper", "graphql", "sync", "import", "export"],
            "debugger": ["debugger", "error", "exception", "traceback", "crash", "bug"],
            "flash": ["flash", "slow", "optimize", "n+1", "query", "bottleneck"],
            "archer": ["archer", "find", "search", "how does", "pattern", "example"],
            "refactor": ["refactor", "bulk", "rename", "restructure", "cleanup"],
            "planner": ["planner", "design", "architecture", "workflow", "strategy"],
            "phoenix": ["phoenix", "upgrade", "migration", "compatibility"],
            "gpt": ["gpt", "large file", "huge context", "complex review", "expert opinion"],
        }

    def analyze_task(self, task_description: str, context_files: List[str] = None, 
                    user_preference: Optional[str] = None, file_count: Optional[int] = None) -> TaskAnalysis:
        """Analyze a task and recommend agent/model"""
        
        reasoning = []
        context_files = context_files or []
        
        # 1. Determine task complexity
        complexity = self._assess_complexity(task_description, context_files, reasoning)
        
        # 2. Check if large implementation based on file count
        if file_count and file_count > 15:
            agent = "gpt"
            reasoning.append(f"Large implementation scope ({file_count} files) - routing to GPT agent")
        else:
            # 3. Find best agent match
            agent = self._find_best_agent(task_description, reasoning)
        
        # 4. Select optimal model
        model = self._select_model(complexity, agent, len(context_files), reasoning)
        
        # 5. Apply user preferences
        if user_preference:
            if user_preference in ["fast", "cheap"]:
                model = ModelTier.HAIKU
                reasoning.append(f"User requested {user_preference} execution")
            elif user_preference in ["quality", "best"]:
                model = ModelTier.OPUS
                reasoning.append(f"User requested {user_preference} results")
        
        # 6. Check GPT offload recommendation
        gpt_offload = self._should_offload_to_gpt(task_description, agent, complexity, file_count, reasoning)
        
        # 7. Calculate estimated tokens
        tokens = self._estimate_tokens(model, complexity, len(context_files))
        
        # 8. Calculate rate limit impact
        impact = self._calculate_rate_limit_impact(tokens, gpt_offload)
        
        # 9. Calculate confidence
        confidence = self._calculate_confidence(task_description, agent, reasoning)
        
        return TaskAnalysis(
            complexity=complexity,
            recommended_model=model,
            recommended_agent=agent,
            confidence=confidence,
            reasoning=reasoning,
            estimated_tokens=tokens,
            rate_limit_impact=impact,
            gpt_offload_recommended=gpt_offload
        )

    def _assess_complexity(self, task: str, context_files: List[str], reasoning: List[str]) -> TaskComplexity:
        """Assess task complexity based on description and context"""
        
        task_lower = task.lower()
        
        # Check for explicit complexity indicators
        if any(keyword in task_lower for keyword in self.complex_keywords):
            matching = [k for k in self.complex_keywords if k in task_lower]
            reasoning.append(f"Complex keywords found: {matching}")
            return TaskComplexity.COMPLEX
            
        if any(keyword in task_lower for keyword in self.simple_keywords):
            matching = [k for k in self.simple_keywords if k in task_lower]
            reasoning.append(f"Simple keywords found: {matching}")
            return TaskComplexity.SIMPLE
        
        # Check context size
        if len(context_files) > 10:
            reasoning.append(f"Large context: {len(context_files)} files")
            return TaskComplexity.COMPLEX
        elif len(context_files) > 3:
            reasoning.append(f"Medium context: {len(context_files)} files")
            return TaskComplexity.MEDIUM
            
        # Default to medium for development tasks
        reasoning.append("Standard development task complexity")
        return TaskComplexity.MEDIUM

    def _find_best_agent(self, task: str, reasoning: List[str]) -> str:
        """Find the best agent for the task"""
        
        task_lower = task.lower()
        best_agent = "scout"  # Default
        best_score = 0
        
        # Check for large implementation patterns that should go to GPT
        large_impl_keywords = [
            "implement complete", "generate entire", "create full", 
            "build comprehensive", "develop whole", "mass generation"
        ]
        if any(keyword in task_lower for keyword in large_impl_keywords):
            reasoning.append("Large implementation detected - routing to GPT agent")
            return "gpt"
        
        for agent_name, patterns in self.task_patterns.items():
            # Skip the agent name itself, check the keywords
            keywords = patterns[1:]  # First item is agent name
            score = sum(1 for keyword in keywords if keyword in task_lower)
            if score > best_score:
                best_score = score
                best_agent = agent_name
        
        if best_score > 0:
            matching_patterns = [p for p in self.task_patterns[best_agent][1:] if p in task_lower]
            reasoning.append(f"Agent {best_agent} selected (patterns: {matching_patterns})")
        else:
            reasoning.append("Using default agent (scout) - no clear pattern match")
            
        return best_agent

    def _select_model(self, complexity: TaskComplexity, agent: str, 
                     context_size: int, reasoning: List[str]) -> ModelTier:
        """Select optimal model based on complexity and agent"""
        
        # Get agent default
        default_model = self.agent_config.get(agent, {}).get("default_model", ModelTier.SONNET)
        
        # Adjust based on complexity
        if complexity == TaskComplexity.SIMPLE:
            if default_model == ModelTier.OPUS:
                model = ModelTier.SONNET  # Downgrade from Opus
                reasoning.append("Downgraded from Opus to Sonnet for simple task")
            elif default_model == ModelTier.SONNET:
                model = ModelTier.HAIKU   # Downgrade from Sonnet  
                reasoning.append("Downgraded from Sonnet to Haiku for simple task")
            else:
                model = default_model
        elif complexity == TaskComplexity.COMPLEX:
            if default_model == ModelTier.HAIKU:
                model = ModelTier.SONNET  # Upgrade from Haiku
                reasoning.append("Upgraded from Haiku to Sonnet for complex task")
            elif default_model == ModelTier.SONNET:
                model = ModelTier.OPUS    # Upgrade from Sonnet
                reasoning.append("Upgraded from Sonnet to Opus for complex task")
            else:
                model = default_model
        else:
            model = default_model
            reasoning.append(f"Using {agent} default model: {model.value}")
        
        # Large context needs more capable model
        if context_size > 20 and model == ModelTier.HAIKU:
            model = ModelTier.SONNET
            reasoning.append("Upgraded to Sonnet for large context")
            
        return model

    def _should_offload_to_gpt(self, task: str, agent: str, complexity: TaskComplexity, 
                               file_count: Optional[int], reasoning: List[str]) -> bool:
        """Determine if task should be offloaded to GPT to save Claude tokens"""
        
        task_lower = task.lower()
        
        # Already routing to GPT agent
        if agent == "gpt":
            reasoning.append("Already routing to GPT agent")
            return True
            
        # Check for GPT offload keywords
        if any(keyword in task_lower for keyword in self.gpt_offload_keywords):
            reasoning.append("GPT offload keywords detected - pattern following task")
            return True
            
        # Large file count
        if file_count and file_count > 15:
            reasoning.append(f"Large file count ({file_count}) - offload to GPT recommended")
            return True
            
        # Complex implementation tasks
        if complexity == TaskComplexity.COMPLEX and "implement" in task_lower:
            reasoning.append("Complex implementation - consider GPT offload")
            return True
            
        return False

    def _estimate_tokens(self, model: ModelTier, complexity: TaskComplexity, context_files: int) -> str:
        """Estimate token usage for the task"""
        
        # Base token estimates
        base_tokens = {
            (ModelTier.HAIKU, TaskComplexity.SIMPLE): (1000, 5000),
            (ModelTier.HAIKU, TaskComplexity.MEDIUM): (5000, 15000),
            (ModelTier.HAIKU, TaskComplexity.COMPLEX): (15000, 30000),
            (ModelTier.SONNET, TaskComplexity.SIMPLE): (5000, 15000),
            (ModelTier.SONNET, TaskComplexity.MEDIUM): (15000, 50000),
            (ModelTier.SONNET, TaskComplexity.COMPLEX): (50000, 150000),
            (ModelTier.OPUS, TaskComplexity.SIMPLE): (10000, 30000),
            (ModelTier.OPUS, TaskComplexity.MEDIUM): (30000, 100000),
            (ModelTier.OPUS, TaskComplexity.COMPLEX): (100000, 300000),
        }
        
        min_tokens, max_tokens = base_tokens.get((model, complexity), (10000, 50000))
        
        # Adjust for context files
        if context_files > 10:
            min_tokens *= 1.5
            max_tokens *= 2
            
        # Format with K/M suffix
        def format_tokens(n):
            if n >= 1_000_000:
                return f"{n/1_000_000:.1f}M"
            elif n >= 1000:
                return f"{n/1000:.0f}K"
            else:
                return str(n)
                
        return f"{format_tokens(min_tokens)}-{format_tokens(max_tokens)} tokens"

    def _calculate_rate_limit_impact(self, tokens: str, gpt_offload: bool) -> str:
        """Calculate impact on Claude rate limit"""
        
        if gpt_offload:
            return "NONE (offloaded to GPT)"
            
        # Parse token range
        token_range = tokens.split("-")[1].strip().split()[0]
        
        # Convert to number
        if "M" in token_range:
            max_tokens = float(token_range.replace("M", "")) * 1_000_000
        elif "K" in token_range:
            max_tokens = float(token_range.replace("K", "")) * 1000
        else:
            max_tokens = float(token_range)
            
        # Rate limit impact categories
        if max_tokens < 10_000:
            return "LOW (minimal impact)"
        elif max_tokens < 50_000:
            return "MEDIUM (noticeable usage)"
        elif max_tokens < 150_000:
            return "HIGH (significant usage)"
        else:
            return "CRITICAL (consider GPT offload!)"

    def _calculate_confidence(self, task: str, agent: str, reasoning: List[str]) -> float:
        """Calculate confidence in the recommendation"""
        
        confidence = 0.5  # Base confidence
        
        # Higher confidence for clear agent matches
        if any("patterns:" in r for r in reasoning):
            confidence += 0.3
            
        # Higher confidence for clear complexity indicators  
        if any("keywords found:" in r for r in reasoning):
            confidence += 0.2
            
        # Lower confidence for default selections
        if any("default" in r.lower() for r in reasoning):
            confidence -= 0.1
            
        return min(max(confidence, 0.1), 1.0)

    def generate_task_prompt(self, analysis: TaskAnalysis, task_description: str, 
                           additional_context: str = "") -> str:
        """Generate optimized prompt for the task"""
        
        agent_doc = f"@docs/agents/{analysis.recommended_agent}.md"
        model_override = f"Model: {analysis.recommended_model.value}"
        
        # Add shared tools for specific scenarios
        shared_tools = ""
        if analysis.recommended_agent == "debugger" and "access" in task_description.lower():
            shared_tools = "\n@docs/agents/SHARED_TOOLS.md"
        
        prompt = f"""{agent_doc}{shared_tools}

{model_override}

{task_description}"""
        
        if additional_context:
            prompt += f"\n\nAdditional context:\n{additional_context}"
            
        return prompt

    def explain_recommendation(self, analysis: TaskAnalysis) -> str:
        """Generate human-readable explanation"""
        
        offload_msg = "✅ YES - Offload to GPT!" if analysis.gpt_offload_recommended else "❌ No - Keep with Claude"
        
        return f"""
🎯 Task Analysis Results:

**Recommended Agent**: {analysis.recommended_agent}
**Recommended Model**: {analysis.recommended_model.value}
**Complexity**: {analysis.complexity.value}
**Estimated Tokens**: {analysis.estimated_tokens}
**Rate Limit Impact**: {analysis.rate_limit_impact}
**GPT Offload**: {offload_msg}
**Confidence**: {analysis.confidence:.1%}

**Reasoning**:
{chr(10).join(f"• {reason}" for reason in analysis.reasoning)}

**Why this matters**:
• Right agent = domain expertise
• Right model = token efficiency
• GPT offload = preserve Claude rate limit
• Smart routing = avoid hitting 5-hour limit!
"""


def demo_smart_routing():
    """Demonstrate smart context management with token optimization"""
    
    manager = SmartContextManager()
    
    test_cases = [
        ("Write unit tests for the motor model", []),
        ("Find how Odoo implements graph views", []),
        ("Debug this complex race condition in order processing", ["order.py", "queue.py", "worker.py"]),
        ("Check container status", []),
        ("Implement complete product variant system with 50+ fields", ["file{}.py".format(i) for i in range(20)]),
        ("Create a product selector component", []),
        ("Quick code quality check on current file", ["current.py"]),
        ("Generate entire Shopify sync module following our patterns", []),
    ]
    
    print("🧠 Smart Context Management Demo (Token Optimization)")
    print("=" * 60)
    print("GOAL: Preserve Claude rate limit by intelligent routing!\n")
    
    total_claude_tokens = 0
    total_gpt_tokens = 0
    
    for task, files in test_cases:
        analysis = manager.analyze_task(task, files, file_count=len(files))
        print(f"\n📋 Task: '{task[:50]}{'...' if len(task) > 50 else ''}'")
        print(f"🎯 Route: {analysis.recommended_agent} + {analysis.recommended_model.value}")
        print(f"🔢 Tokens: {analysis.estimated_tokens}")
        print(f"⚠️  Impact: {analysis.rate_limit_impact}")
        
        if analysis.gpt_offload_recommended:
            print("✅ OFFLOAD TO GPT - Saves Claude tokens!")
        
        print(f"📊 Confidence: {analysis.confidence:.1%}")
    
    print("\n" + "=" * 60)
    print("💡 With smart routing, complex implementations go to GPT,")
    print("   preserving your Claude rate limit for what it does best!")


if __name__ == "__main__":
    demo_smart_routing()