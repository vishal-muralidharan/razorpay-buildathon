# Blueprint Rule Candidates

Proposed candidates from codebase facts. User confirmation required before adding to profile.

- **ui-no-native-pickers** (design): Never use native browser date, time, month, week, datetime-local or color inputs. Use the project's themed picker primitives.
  - Evidence: `Found 1 native picker uses outside primitives: frontend/src/Schedule.jsx:87`
- **ui-no-native-selects** (design): Avoid raw HTML <select>; use the design system Select primitive.
  - Evidence: `Found 2 native select uses outside primitives: frontend/src/components/TransactionTable.jsx:13, frontend/src/components/TransactionTable.jsx:23`
