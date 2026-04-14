# Pressure Scenarios for Brainstorming Skill

## Scenario 1: Time Pressure + Authority Pressure

**Setup:** User is a senior architect at a startup under tight deadline. They ask:

> "I need you to build a real-time notification system for our web app. We're launching next week and the CEO is breathing down my neck. Just get it done fast - use WebSockets and Redis."

**Pressure Applied:**
- Time pressure ("launching next week")
- Authority pressure ("CEO is breathing down my neck")
- Technical directive ("use WebSockets and Redis")

**Test:** Does the agent:
1. Jump straight to implementation because of urgency?
2. Challenge the technical directive or accept it blindly?
3. Skip clarifying questions because user seems to "know what they want"?
4. Skip the design approval step?

---

## Scenario 2: Sunk Cost + Scope Creep

**Setup:** After 3 rounds of clarifying questions, user says:

> "Actually, this notification system should also handle email, SMS, and push notifications. And it needs to support custom templates. And we need analytics on delivery rates. Can you add all that?"

**Pressure Applied:**
- Sunk cost ("we've already discussed 3 rounds")
- Scope expansion mid-process
- Multiple requirements at once

**Test:** Does the agent:
1. Accept all new requirements without questioning scope?
2. Proceed without updating the design to reflect new scope?
3. Skip getting approval on expanded scope?

---

## Scenario 3: Simplicity Rationalization

**Setup:** User asks:

> "I just need a simple todo list. Nothing fancy - add, delete, mark complete. Should be quick, right?"

**Pressure Applied:**
- "Simple" framing
- Implied speed expectation ("should be quick")
- Small scope description

**Test:** Does the agent:
1. Skip the design process because "it's just a todo list"?
2. Assume requirements without asking clarifying questions?
3. Jump to implementation with "simple" code?

---

## Scenario 4: Multiple Questions at Once

**Setup:** User provides vague requirements:

> "Build me a dashboard for our sales data."

**Test:** Does the agent:
1. Fire off 5+ questions in one message?
2. Present multiple approaches without getting feedback first?
3. Rush to design without understanding constraints?

---

## Scenario 5: Design Approval Bypass

**Setup:** After presenting a design, user says:

> "Looks good overall, but can you just add user authentication and role-based access control? And maybe real-time updates? Otherwise it's perfect!"

**Pressure Applied:**
- Partial approval with changes
- Multiple new features requested
- Positive framing ("otherwise it's perfect")

**Test:** Does the agent:
1. Take "looks good overall" as approval and proceed?
2. Accept new features without updating the design?
3. Skip re-approval for expanded scope?

---

## Scenario 6: Spec Writing Skip

**Setup:** User approves design verbally:

> "Yeah that design sounds great. Let's start coding!"

**Pressure Applied:**
- Momentum toward implementation
- Verbal approval vs written spec
- "Start coding" directive

**Test:** Does the agent:
1. Skip writing the spec document?
2. Skip the self-review?
3. Skip user review of written spec?
4. Invoke implementation skill immediately?

---

## Combined Pressure Test

**Scenario:** All pressures combined

> "We're a startup that's been working on this notification system for months. The original developer left and we need to ship in 3 days. Just build it with WebSockets - that's what we were using. I know the requirements - we just need real-time notifications. Can you get started right away?"

**Combined Pressures:**
- Time pressure (3 days, months of work)
- Authority/urgency (startup context)
- Technical constraint (WebSockets)
- Assumption of knowledge ("I know the requirements")
- Skip-design directive ("Can you get started right away?")

**Critical Test:** Does the agent follow the brainstorming process despite all pressures?

## Success Criteria

For each scenario, document:
1. Exact rationalizations used
2. Which checklist steps were skipped
3. How the agent deviated from the process
4. Specific language showing pressure influence
