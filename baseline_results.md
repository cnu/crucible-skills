# Baseline Test Results

## Summary

Tested 4 scenarios with subagents WITHOUT the brainstorming skill to document natural behavior.

## Key Findings

### Finding 1: Multiple Questions Violation (HIGH SEVERITY)
**Scenario:** "Build me a dashboard for our sales data" (vague request)

**Behavior:** Agent asked 6 questions at once in a bullet list format:
- Technology Stack
- Data Source  
- Key Metrics
- Visualization Types
- Layout/Design
- Interactivity

**Rationalization:** "asked all at once in a single response so you can answer them together"

**Impact:** Overwhelms user, prevents incremental refinement, leads to incomplete answers

### Finding 2: Urgency Pressure Response (MEDIUM SEVERITY)
**Scenario:** Startup with 3-day deadline, CEO pressure, "get started right away"

**Behavior:** Agent asked questions but showed scattered approach:
- Acknowledged urgency
- Asked 8 questions in rapid sequence
- Mixed technical and product questions
- No systematic exploration

**Rationalization:** "my job is to find the minimal viable thing that actually ships"

**Impact:** Missing structured approach leads to skipped steps later

### Finding 3: Partial Approval Handling (LOW SEVERITY)
**Scenario:** User says "looks good overall" but requests changes

**Behavior:** Agent asked clarifying questions about the new requirements
- Asked about authentication mechanism
- Asked about RBAC details
- Confirmed understanding before proceeding

**Good:** Didn't take partial approval as full approval
**Concern:** Didn't explicitly state need to update design document

### Finding 4: Simplicity Trap (MEDIUM SEVERITY)
**Scenario:** "Just a simple todo list, should be quick"

**Behavior:** Agent recognized context and asked where to integrate
- Asked one question about integration
- Didn't explore scope or requirements

**Rationalization:** Implicit - treating it as "simple" means fewer questions needed

**Impact:** Insufficient requirements gathering for even "simple" features

## Critical Violations to Address in Skill

1. **Multiple questions at once** - Must enforce single-question rule
2. **Skipping design approval** - Must get explicit approval
3. **Skipping spec document** - Must write and review
4. **No approach exploration** - Must present 2-3 options with trade-offs
5. **"Simple" rationalization** - Must treat all projects equally

## Rationalizations to Counter

| Excuse | Counter |
|--------|---------|
| "asked all at once so you can answer together" | One question at a time enables incremental refinement |
| "minimal viable thing that ships" | MV requires understanding requirements first |
| "it's just a simple X" | Simple projects have unexamined assumptions too |
| "looks good overall" | Need explicit approval on specific design |

## Red Flags Detected

- Bullet lists of questions
- Acknowledging urgency then immediately asking questions
- Not mentioning design document
- Not mentioning approval checkpoints
