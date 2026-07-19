# G2 React Vite State Management
## Purpose
Defines the canonical patterns for managing state in React components within a Vite-based project.

## Engineering Standards
- **Local State**: Use `useState` for simple, component-local state.
- **Complex Logic**: Use `useReducer` for complex state transitions or multiple related state variables.
- **Context API**: Use `useContext` for global/shared state (e.g., Auth, Theme).
- **External State**: Use Zustand or Redux Toolkit for large-scale application state.

## Implementation Rules
- **State Shape**: Use TypeScript union types for complex states (e.g., `idle | loading | success | error`).
- **Side Effects**: Use `useEffect` for side effects, ensuring proper cleanup functions are provided.
- **Derived State**: Calculate derived state during render rather than storing it in state.
- **Async Actions**: Handle async operations within `useEffect` or custom hooks, updating state based on the result.
