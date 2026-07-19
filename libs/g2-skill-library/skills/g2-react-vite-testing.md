# G2 React Vite Testing
## Purpose
Defines the canonical testing standards for React components in a Vite-based project.

## Engineering Standards
- **Unit Testing**: Use Vitest for logic and utility function testing.
- **Component Testing**: Use React Testing Library (RTL) for component behavior tests.
- **Integration Testing**: Test key user flows and interactions between multiple components.
- **E2E Testing**: Use Playwright or Cypress for critical path testing.

## Implementation Rules
- **act() Helper**: Wrap all renders and updates in `await act()` to ensure pending state updates are flushed before assertions.
- **User Events**: Use `@testing-library/user-event` for simulating realistic user interactions.
- **Mocking**: Mock external API calls and complex dependencies using Vitest mocks.
- **Snapshot Testing**: Use sparingly; prioritize behavior-based assertions over snapshot matching.
- **Coverage**: Aim for high coverage on business logic and critical UI paths.
