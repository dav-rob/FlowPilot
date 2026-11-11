### FlowPilot — Intelligent Enterprise AI Automation

FlowPilot  uses autonomous AI tool selection and iterative reasoning toinvestigates business problems and recommends appropriate actions, rather than simply following predefined workflows. It is designed for situations where incoming emails, documents or events require information to be gathered from several business systems before a decision can be made. It investigates:

- suspected supplier fraud, 
- checks regulatory compliance, 
- handle personal-data requests, 
- identify IT security issues,
- assess contract changes. 

The application uses data that models a financial-services organisation.

An incoming document is classified using a language model or the decision model JEV classification service to determine which business processes are relevant. An AI model then decides which tools to call, with what arguments, examines the results and determines what to do next. This continues until the application has gathered sufficient evidence to reach a conclusion or escalate the investigation. The system provides 63 callable business tools and can execute independent information-gathering operations in parallel. It also supports intelligent model routing, using cheaper, faster models for routine work and escalating to more capable reasoning models when investigations become complex or evidence is contradictory.

The application is built using Python, FastAPI, React, TypeScript, asyncio and SQLite, with integrations to AI models through locally authenticated Claude, Codex and Antigravity CLIs. An important architectural feature is that the AI can dynamically decide what to investigate, but cannot bypass the application's security and governance controls. Tool access is restricted, arguments are validated, evidence is traceable, and consequential actions require explicit human approval. Every investigation is recorded for inspection and replay, with an evaluation framework measuring accuracy, evidence quality, tool usage and safety. The current implementation is a working local demonstration using synthetic enterprise systems, rather than a production deployment.
