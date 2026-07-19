# G2 React Vite Component Structure
## Purpose
Defines the canonical structure for React components within a Vite-based project.

## Engineering Standards
- **Functional Components**: Use functional components with Hooks exclusively.
- **Prop Types**: Mandatory TypeScript interfaces for all props.
- **Decomposition**: Components must be small and focused on a single responsibility.
- **Naming**: PascalCase for components, camelCase for internal functions/variables.
- **Styling**: Use CSS Modules or Tailwind classes as defined in project profile.

## Implementation Rules
- **Hooks**: Place hooks at the top level of the component.
- **Sub-components**: Extract complex logic into custom hooks or sub-components.
- **Ref handling**: Use `useRef` for DOM access, avoiding direct manipulation where possible.
- **Memoization**: Use `useMemo` and `useCallback` only when performance profiling indicates a need.
