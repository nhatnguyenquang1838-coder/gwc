# G2 React Vite Performance
## Purpose
Defines the canonical performance optimization standards for React components in a Vite-based project.

## Engineering Standards
- **React Compiler**: Use the React Compiler (`reactCompilerPreset`) for automatic memoization where applicable.
- **Lazy Loading**: Use `React.lazy` and `Suspense` for route-level or heavy component loading.
- **Bundle Size**: Monitor bundle size; avoid large libraries in the main thread if possible.
- **Image Optimization**: Use modern formats (WebP/Avif) and responsive sizes.

## Implementation Rules
- **Memoization**: Use `useMemo` for expensive calculations and `useCallback` to stabilize function references passed to memoized components.
- **Virtualization**: Use virtualization for long lists or large data sets.
- **Debouncing/Throttling**: Apply debouncing to search inputs and throttling to scroll/resize events.
- **Vite Optimization**: Leverage Vite's build-time optimizations (e.g., `manualChunks`).
