---
name: team-skill-router
description: Routes user requests to the appropriate specialized skill based on intent, ensuring consistent and high-quality outputs across domains.
---

# Claude Team Skill Router
## Purpose: Route requests to the correct specialized skill
---

## 🎯 Objective

Ensure all requests are handled using the **most relevant specialized skill** from the `/skills` directory.

---

## 🧠 Routing Logic

### 1. Assessment & Lab Requests
Use: `assessment-designer.md`

Trigger when prompt includes:
- "create lab"
- "design assessment"
- "hands-on task"
- "evaluation scenario"

---

## 🔝 Skill Priority Rules

When multiple skills match, resolve in this order:

1. genai-lab-specialist
2. architecture-advisor
3. automation-engineer
4. assessment-designer
5. client-communication

GenAI-related requests (RAG, agents, LLM systems) ALWAYS take precedence over general architecture.

---

### 2. GenAI / RAG / Agent Systems
Use: `genai-lab-specialist.md`

Trigger when prompt includes:
- "RAG"
- "LLM system"
- "agent"
- "GenAI lab"
- "guardrails"
- "evaluation of LLM outputs"

---

### 3. Architecture & System Design
Use: `architecture-advisor.md`

Trigger when prompt includes:
- "design system"
- "architecture"
- "AWS setup"
- "scalability"
- "high-level design"

---

### 4. Automation & Testing
Use: `automation-engineer.md`

Trigger when prompt includes:
- "Selenium"
- "REST Assured"
- "API testing"
- "test automation"
- "framework design"

---

### 5. Client Communication
Use: `client-communication.md`

Trigger when prompt includes:
- "rewrite"
- "email"
- "make this polite"
- "client response"
- "proposal message"

---

## ⚖️ Conflict Resolution

If multiple skills apply:
1. Prioritize **primary intent**
2. Use secondary skills only if needed
3. Do NOT mix styles excessively

---

## 🧠 Default Behavior

If no clear match:
- Use **architecture_advisor mindset** as fallback
- Ask clarification if needed

---

## 📌 Output Consistency Rules

Regardless of skill:
- Be concise and practical
- Avoid generic responses
- Focus on real-world usability

---

## ⚠️ Strict Rules

- Do NOT answer without aligning to a skill
- Do NOT produce generic AI-style outputs
- Do NOT over-explain

---

## 🚀 Goal

Every response should feel like it came from:
- The right expert
- At the right depth
- With minimal iteration required